#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_AUTHORIZATION_URL = "https://ecyvlzfbufloietjsmtj.supabase.co/auth/v1/oauth/authorize"
DEFAULT_TOKEN_URL = "https://ecyvlzfbufloietjsmtj.supabase.co/auth/v1/token"
DEFAULT_CLIENT_ID = "172c54ca-df94-477c-b28d-826db721b66a"
DEFAULT_RESOURCE = "https://mcp.pika.me/api/mcp"
DEFAULT_SCOPE = "openid profile email phone"
DEFAULT_TOKEN_STORE = "~/.config/moggie/pika_mcp_oauth.json"


def main() -> int:
    default_redirect_uri = _default_redirect_uri()
    parser = argparse.ArgumentParser(description="Authorize Moggie's runtime Pika MCP client.")
    parser.add_argument("--authorization-url", default=os.getenv("MOGGIE_PIKA_MCP_AUTHORIZATION_URL", DEFAULT_AUTHORIZATION_URL))
    parser.add_argument("--token-url", default=os.getenv("MOGGIE_PIKA_MCP_TOKEN_URL", DEFAULT_TOKEN_URL))
    parser.add_argument("--client-id", default=os.getenv("MOGGIE_PIKA_MCP_CLIENT_ID", DEFAULT_CLIENT_ID))
    parser.add_argument("--redirect-uri", default=os.getenv("MOGGIE_PIKA_MCP_REDIRECT_URI", default_redirect_uri))
    parser.add_argument("--scope", default=os.getenv("MOGGIE_PIKA_MCP_SCOPE", DEFAULT_SCOPE))
    parser.add_argument("--resource", default=os.getenv("MOGGIE_PIKA_MCP_RESOURCE", DEFAULT_RESOURCE))
    parser.add_argument("--token-store", default=os.getenv("MOGGIE_PIKA_MCP_TOKEN_STORE", DEFAULT_TOKEN_STORE))
    args = parser.parse_args()

    verifier = _pkce_verifier()
    state = secrets.token_urlsafe(24)
    auth_params = {
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
        "state": state,
        "scope": args.scope,
        "resource": args.resource,
    }
    separator = "&" if "?" in args.authorization_url else "?"
    auth_url = f"{args.authorization_url}{separator}{urlencode(auth_params)}"

    print("Open this Pika MCP authorization URL:")
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

    token_response = _post_form(
        args.token_url,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": args.redirect_uri,
            "client_id": args.client_id,
            "code_verifier": verifier,
        },
    )
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
    print(f"Wrote Pika MCP token store to {token_store}")
    print("Copy this file to the same path on the Pi, owned by the moggie service user, mode 0600.")
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


def _default_redirect_uri() -> str:
    callback_id = secrets.token_urlsafe(9)
    return f"http://127.0.0.1:{_free_local_port()}/callback/{callback_id}"


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


if __name__ == "__main__":
    raise SystemExit(main())
