#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_TOKEN_STORE = "~/.config/moggie/midjourney_oauth.json"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorize Moggie's Midjourney MCP client for headless Pi runtime.")
    parser.add_argument("--authorization-url", default=os.getenv("MOGGIE_MIDJOURNEY_AUTHORIZATION_URL", ""))
    parser.add_argument("--token-url", default=os.getenv("MOGGIE_MIDJOURNEY_TOKEN_URL", ""))
    parser.add_argument("--client-id", default=os.getenv("MOGGIE_MIDJOURNEY_CLIENT_ID", ""))
    parser.add_argument("--client-secret", default=os.getenv("MOGGIE_MIDJOURNEY_CLIENT_SECRET", ""))
    parser.add_argument("--redirect-uri", default=os.getenv("MOGGIE_MIDJOURNEY_REDIRECT_URI", DEFAULT_REDIRECT_URI))
    parser.add_argument("--scope", default=os.getenv("MOGGIE_MIDJOURNEY_SCOPE", ""))
    parser.add_argument("--token-store", default=os.getenv("MOGGIE_MIDJOURNEY_TOKEN_STORE", DEFAULT_TOKEN_STORE))
    args = parser.parse_args()

    if not args.authorization_url or not args.token_url or not args.client_id:
        print(
            "Missing OAuth metadata. Set MOGGIE_MIDJOURNEY_AUTHORIZATION_URL, "
            "MOGGIE_MIDJOURNEY_TOKEN_URL, and MOGGIE_MIDJOURNEY_CLIENT_ID.",
            file=sys.stderr,
        )
        return 2

    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(24)
    auth_params = {
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if args.scope:
        auth_params["scope"] = args.scope
    separator = "&" if "?" in args.authorization_url else "?"
    auth_url = f"{args.authorization_url}{separator}{urlencode(auth_params)}"

    print("Open this Midjourney authorization URL on a phone or laptop:")
    print(auth_url)
    print()
    print("After approval, paste the full final callback URL here.")
    callback_url = input("Callback URL: ").strip()
    parsed = urlparse(callback_url)
    query = parse_qs(parsed.query)
    if query.get("state", [""])[0] != state:
        print("Callback state did not match; refusing to write token store.", file=sys.stderr)
        return 3
    code = query.get("code", [""])[0]
    if not code:
        print("Callback URL did not contain a code parameter.", file=sys.stderr)
        return 4

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": args.redirect_uri,
        "client_id": args.client_id,
        "code_verifier": verifier,
    }
    if args.client_secret:
        token_payload["client_secret"] = args.client_secret
    token_response = _post_form(args.token_url, token_payload)
    access_token = str(token_response.get("access_token") or "").strip()
    if not access_token:
        print("Token endpoint did not return access_token.", file=sys.stderr)
        return 5

    output = {
        "access_token": access_token,
        "refresh_token": str(token_response.get("refresh_token") or ""),
        "token_url": args.token_url,
    }
    if token_response.get("expires_in") is not None:
        output["expires_at"] = time.time() + float(token_response["expires_in"])
    token_store = Path(args.token_store).expanduser()
    token_store.parent.mkdir(parents=True, exist_ok=True)
    token_store.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    token_store.chmod(0o600)
    print(f"Wrote Midjourney token store to {token_store}")
    print("On the Pi, ensure this file is readable by the moggie.service user and not committed.")
    return 0


def _post_form(url: str, fields: dict[str, str]) -> dict[str, object]:
    request = Request(
        url,
        data=urlencode(fields).encode("utf-8"),
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=30) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("Token endpoint returned non-object JSON")
    return decoded


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


if __name__ == "__main__":
    raise SystemExit(main())
