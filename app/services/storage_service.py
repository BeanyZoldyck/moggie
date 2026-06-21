from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import MoggieConfig

class StorageService:
    def __init__(
        self,
        mode: str,
        media_dir: Path,
        *,
        enable_s3_video_storage: bool = False,
        s3_bucket: str = "",
        s3_region: str = "",
        s3_prefix: str = "",
    ) -> None:
        self.mode = mode
        self.media_dir = media_dir
        self.enable_s3_video_storage = enable_s3_video_storage
        self.s3_bucket = s3_bucket
        self.s3_region = s3_region
        self.s3_prefix = s3_prefix.strip("/")
        self._s3_client: Any | None = None

    @classmethod
    def from_config(cls, config: MoggieConfig) -> "StorageService":
        return cls(
            config.storage_mode,
            config.media_dir,
            enable_s3_video_storage=config.enable_s3_video_storage,
            s3_bucket=config.s3_bucket,
            s3_region=config.s3_region,
            s3_prefix=config.s3_prefix,
        )

    def ensure_ready(self) -> None:
        if self.mode in {"local", "usb"}:
            self.media_dir.mkdir(parents=True, exist_ok=True)
        if self.enable_s3_video_storage and (not self.s3_bucket or not self.s3_region):
            raise ValueError("S3 storage is enabled but MOGGIE_S3_BUCKET or MOGGIE_S3_REGION is missing.")

    def upload_video(self, path: Path, game_type: str, session_id: str) -> dict[str, str]:
        if not self.enable_s3_video_storage:
            raise RuntimeError("S3 video storage is disabled.")
        client = self._get_s3_client()
        key = self._build_key(path, game_type, session_id)
        client.upload_file(str(path), self.s3_bucket, key, ExtraArgs={"ContentType": "video/mp4"})
        return {
            "bucket": self.s3_bucket,
            "region": self.s3_region,
            "key": key,
            "url": f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com/{key}",
        }

    def _build_key(self, path: Path, game_type: str, session_id: str) -> str:
        filename = f"{game_type}_{session_id}_{path.stem}.mp4"
        base = f"moggie/{game_type}/{filename}"
        if not self.s3_prefix:
            return base
        return f"{self.s3_prefix}/{base}"

    def _get_s3_client(self) -> Any:
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency validated elsewhere
            raise RuntimeError("boto3 is required for S3 video uploads.") from exc
        self._s3_client = boto3.client("s3", region_name=self.s3_region)
        return self._s3_client
