from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}
ENVIRONMENTS = {"development", "production", "test"}
GAME_MODES = {"versus", "solo", "alternating"}
STORAGE_MODES = {"none", "local", "usb"}
PIKA_PROVIDERS = {"mcp", "fal"}
CAMERA_BACKENDS = {"opencv", "qnx"}
HAND_TRACKING_BACKENDS = {"mediapipe", "simple"}
FACE_TRACKING_BACKENDS = {"mediapipe", "cascade"}


@dataclass(frozen=True)
class MoggieConfig:
    env: str
    fullscreen: bool
    window_width: int
    window_height: int
    target_fps: int
    placeholder_frames: int
    db_path: Path
    enable_redis_leaderboard_cache: bool
    redis_url: str
    redis_leaderboard_ttl_seconds: int
    storage_mode: str
    media_dir: Path
    save_snapshots: bool
    save_generated_media: bool
    enable_s3_video_storage: bool
    s3_bucket: str
    s3_region: str
    s3_prefix: str
    camera_backend: str
    camera_index: int
    camera_width: int
    camera_height: int
    camera_fps: int
    camera_gain: float
    camera_brightness: int
    camera_retry_seconds: int
    qnx_camera_grabber: Path
    qnx_camera_unit: int
    qnx_camera_decimate: int
    cv_width: int
    cv_height: int
    cv_fps: int
    cv_enable_face_detection: bool
    hand_tracking_backend: str
    face_tracking_backend: str
    idle_attract_enabled: bool
    idle_timeout_seconds: int
    attract_rotation_seconds: int
    default_game_mode: str
    enable_fixed_half_zones: bool
    zone_split_x: float
    show_zone_divider: bool
    allow_manual_start_override: bool
    sixty_seven_mode: str
    sixty_seven_max_hands: int
    sixty_seven_round_seconds: int
    sixty_seven_require_both_hands: bool
    sixty_seven_min_confidence: float
    sixty_seven_rep_cooldown_ms: int
    sixty_seven_extend_threshold: float
    sixty_seven_return_threshold: float
    sixty_seven_min_swing: float
    emoji_mode: str
    emoji_max_faces: int
    emoji_round_seconds: int
    emoji_enable_tongue_out: bool
    emoji_use_cloud_validation: bool
    enable_pika: bool
    enable_image_generation: bool
    enable_midjourney: bool
    midjourney_mcp_url: str
    midjourney_token_store: Path
    midjourney_client_id: str
    midjourney_client_secret: str
    enable_llm_labels: bool
    enable_qnx_subsystem: bool
    pika_provider: str
    pika_mcp_url: str
    pika_mcp_bearer_token: str
    pika_mcp_token_store: Path
    pika_mcp_generation_tool: str
    pika_mcp_upload_tool: str
    fal_key: str
    pika_model: str
    ai_timeout_seconds: int
    ai_poll_interval_seconds: int
    enable_voice: bool
    deepgram_api_key: str
    deepgram_voice_model: str
    enable_social_posting: bool
    default_post_platform: str
    x_api_key: str
    x_api_key_secret: str
    x_access_token: str
    x_access_token_secret: str
    deepgram_voice_agent_endpoint: str
    voice_agent_mic_sample_rate: int
    voice_agent_mic_input_device: str

    @property
    def display_size(self) -> tuple[int, int]:
        return self.window_width, self.window_height


def load_config(environ: Mapping[str, str] | None = None) -> MoggieConfig:
    env = environ if environ is not None else _load_environment()
    app_env = _enum(env, "MOGGIE_ENV", "development", ENVIRONMENTS)

    return MoggieConfig(
        env=app_env,
        fullscreen=_bool(env, "MOGGIE_FULLSCREEN", False),
        window_width=_int(env, "MOGGIE_WINDOW_WIDTH", 1280, 320, 7680),
        window_height=_int(env, "MOGGIE_WINDOW_HEIGHT", 720, 240, 4320),
        target_fps=_int(env, "MOGGIE_TARGET_FPS", 30, 1, 120),
        placeholder_frames=_int(env, "MOGGIE_PLACEHOLDER_FRAMES", 0, 0, 1_000_000),
        db_path=_path(env, "MOGGIE_DB_PATH", "./data/moggie.sqlite"),
        enable_redis_leaderboard_cache=_bool(env, "MOGGIE_ENABLE_REDIS_LEADERBOARD_CACHE", True),
        redis_url=_str(env, "MOGGIE_REDIS_URL", "redis://localhost:6379/0"),
        redis_leaderboard_ttl_seconds=_int(env, "MOGGIE_REDIS_LEADERBOARD_TTL_SECONDS", 30, 1, 3600),
        storage_mode=_enum(env, "MOGGIE_STORAGE_MODE", "none", STORAGE_MODES),
        media_dir=_path(env, "MOGGIE_MEDIA_DIR", "./media"),
        save_snapshots=_bool(env, "MOGGIE_SAVE_SNAPSHOTS", False),
        save_generated_media=_bool(env, "MOGGIE_SAVE_GENERATED_MEDIA", False),
        enable_s3_video_storage=_bool(env, "MOGGIE_ENABLE_S3_VIDEO_STORAGE", False),
        s3_bucket=_str(env, "MOGGIE_S3_BUCKET", ""),
        s3_region=_str(env, "MOGGIE_S3_REGION", ""),
        s3_prefix=_str(env, "MOGGIE_S3_PREFIX", ""),
        camera_backend=_enum(env, "MOGGIE_CAMERA_BACKEND", "opencv", CAMERA_BACKENDS),
        camera_index=_int(env, "MOGGIE_CAMERA_INDEX", 0, 0, 16),
        camera_width=_int(env, "MOGGIE_CAMERA_WIDTH", 640, 160, 3840),
        camera_height=_int(env, "MOGGIE_CAMERA_HEIGHT", 480, 120, 2160),
        camera_fps=_int(env, "MOGGIE_CAMERA_FPS", 30, 1, 120),
        camera_gain=_float(env, "MOGGIE_CAMERA_GAIN", 1.0, 0.2, 4.0),
        camera_brightness=_int(env, "MOGGIE_CAMERA_BRIGHTNESS", 0, -100, 100),
        camera_retry_seconds=_int(env, "MOGGIE_CAMERA_RETRY_SECONDS", 3, 1, 60),
        qnx_camera_grabber=_path(env, "MOGGIE_QNX_CAMERA_GRABBER", "./moggi_camgrab"),
        qnx_camera_unit=_int(env, "MOGGIE_QNX_CAMERA_UNIT", 1, 1, 4),
        qnx_camera_decimate=_int(env, "MOGGIE_QNX_CAMERA_DECIMATE", 3, 1, 8),
        cv_width=_int(env, "MOGGIE_CV_WIDTH", 320, 80, 1920),
        cv_height=_int(env, "MOGGIE_CV_HEIGHT", 240, 60, 1080),
        cv_fps=_int(env, "MOGGIE_CV_FPS", 15, 1, 60),
        cv_enable_face_detection=_bool(env, "MOGGIE_CV_ENABLE_FACE_DETECTION", True),
        hand_tracking_backend=_enum(env, "MOGGIE_HAND_TRACKING_BACKEND", "mediapipe", HAND_TRACKING_BACKENDS),
        face_tracking_backend=_enum(env, "MOGGIE_FACE_TRACKING_BACKEND", "mediapipe", FACE_TRACKING_BACKENDS),
        idle_attract_enabled=_bool(env, "MOGGIE_IDLE_ATTRACT_ENABLED", True),
        idle_timeout_seconds=_int(env, "MOGGIE_IDLE_TIMEOUT_SECONDS", 90, 5, 3600),
        attract_rotation_seconds=_int(env, "MOGGIE_ATTRACT_ROTATION_SECONDS", 8, 2, 120),
        default_game_mode=_enum(env, "MOGGIE_DEFAULT_GAME_MODE", "versus", GAME_MODES),
        enable_fixed_half_zones=_bool(env, "MOGGIE_ENABLE_FIXED_HALF_ZONES", True),
        zone_split_x=_float(env, "MOGGIE_ZONE_SPLIT_X", 0.5, 0.05, 0.95),
        show_zone_divider=_bool(env, "MOGGIE_SHOW_ZONE_DIVIDER", True),
        allow_manual_start_override=_bool(env, "MOGGIE_ALLOW_MANUAL_START_OVERRIDE", True),
        sixty_seven_mode=_enum(env, "MOGGIE_67_MODE", "versus", GAME_MODES),
        sixty_seven_max_hands=_int(env, "MOGGIE_67_MAX_HANDS", 4, 1, 4),
        sixty_seven_round_seconds=_int(env, "MOGGIE_67_ROUND_SECONDS", 20, 5, 180),
        sixty_seven_require_both_hands=_bool(env, "MOGGIE_67_REQUIRE_BOTH_HANDS", False),
        sixty_seven_min_confidence=_float(env, "MOGGIE_67_MIN_CONFIDENCE", 0.55, 0.0, 1.0),
        sixty_seven_rep_cooldown_ms=_int(env, "MOGGIE_67_REP_COOLDOWN_MS", 350, 0, 5000),
        sixty_seven_extend_threshold=_float(env, "MOGGIE_67_EXTEND_THRESHOLD", 0.34, 0.05, 1.0),
        sixty_seven_return_threshold=_float(env, "MOGGIE_67_RETURN_THRESHOLD", 0.30, 0.05, 1.0),
        sixty_seven_min_swing=_float(env, "MOGGIE_67_MIN_SWING", 0.04, 0.0, 1.0),
        emoji_mode=_enum(env, "MOGGIE_EMOJI_MODE", "versus", GAME_MODES),
        emoji_max_faces=_int(env, "MOGGIE_EMOJI_MAX_FACES", 2, 1, 2),
        emoji_round_seconds=_int(env, "MOGGIE_EMOJI_ROUND_SECONDS", 30, 5, 180),
        emoji_enable_tongue_out=_bool(env, "MOGGIE_EMOJI_ENABLE_TONGUE_OUT", False),
        emoji_use_cloud_validation=_bool(env, "MOGGIE_EMOJI_USE_CLOUD_VALIDATION", False),
        enable_pika=_bool(env, "MOGGIE_ENABLE_PIKA", False),
        enable_image_generation=_bool(env, "MOGGIE_ENABLE_IMAGE_GENERATION", True),
        enable_midjourney=_bool(env, "MOGGIE_ENABLE_MIDJOURNEY", True),
        midjourney_mcp_url=_str(env, "MOGGIE_MIDJOURNEY_MCP_URL", "https://mcp.midjourney.com/mcp"),
        midjourney_token_store=_path(
            env,
            "MOGGIE_MIDJOURNEY_TOKEN_STORE",
            "~/.config/moggie/midjourney_oauth.json",
            expand_user=True,
        ),
        midjourney_client_id=_str(env, "MOGGIE_MIDJOURNEY_CLIENT_ID", ""),
        midjourney_client_secret=_str(env, "MOGGIE_MIDJOURNEY_CLIENT_SECRET", ""),
        enable_llm_labels=_bool(env, "MOGGIE_ENABLE_LLM_LABELS", False),
        enable_qnx_subsystem=_bool(env, "MOGGIE_ENABLE_QNX_SUBSYSTEM", False),
        pika_provider=_enum(env, "MOGGIE_PIKA_PROVIDER", "mcp", PIKA_PROVIDERS),
        pika_mcp_url=_str(env, "MOGGIE_PIKA_MCP_URL", "https://mcp.pika.me/api/mcp"),
        pika_mcp_bearer_token=_str(env, "MOGGIE_PIKA_MCP_BEARER_TOKEN", ""),
        pika_mcp_token_store=_path(
            env,
            "MOGGIE_PIKA_MCP_TOKEN_STORE",
            "~/.config/moggie/pika_mcp_oauth.json",
            expand_user=True,
        ),
        pika_mcp_generation_tool=_str(env, "MOGGIE_PIKA_MCP_GENERATION_TOOL", ""),
        pika_mcp_upload_tool=_str(env, "MOGGIE_PIKA_MCP_UPLOAD_TOOL", ""),
        fal_key=_str(env, "FAL_KEY", ""),
        pika_model=_str(env, "MOGGIE_PIKA_MODEL", "fal-ai/pika/v2/turbo/image-to-video"),
        ai_timeout_seconds=_int(env, "MOGGIE_AI_TIMEOUT_SECONDS", 45, 1, 300),
        ai_poll_interval_seconds=_int(env, "MOGGIE_AI_POLL_INTERVAL_SECONDS", 2, 1, 30),
        enable_voice=_bool(env, "MOGGIE_ENABLE_VOICE", True),
        deepgram_api_key=_str(env, "DEEPGRAM_API_KEY", ""),
        deepgram_voice_model=_str(env, "MOGGIE_DEEPGRAM_VOICE_MODEL", "aura-2-atlas-en"),
        enable_social_posting=_bool(env, "MOGGIE_ENABLE_SOCIAL_POSTING", False),
        default_post_platform=_str(env, "MOGGIE_DEFAULT_POST_PLATFORM", "x"),
        x_api_key=_str(env, "X_API_KEY", ""),
        x_api_key_secret=_str(env, "X_API_KEY_SECRET", ""),
        x_access_token=_str(env, "X_ACCESS_TOKEN", ""),
        x_access_token_secret=_str(env, "X_ACCESS_TOKEN_SECRET", ""),
        deepgram_voice_agent_endpoint=_str(
            env,
            "MOGGIE_DEEPGRAM_VOICE_AGENT_ENDPOINT",
            "wss://agent.deepgram.com/v1/agent/converse",
        ),
        voice_agent_mic_sample_rate=_int(env, "MOGGIE_VOICE_AGENT_MIC_SAMPLE_RATE", 16000, 8000, 48000),
        voice_agent_mic_input_device=_str(env, "MOGGIE_VOICE_AGENT_INPUT_DEVICE", ""),
    )


def _str(env: Mapping[str, str], key: str, default: str) -> str:
    return env.get(key, default).strip()


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ConfigError(f"{key} must be a boolean value, got {raw!r}")


def _int(env: Mapping[str, str], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    return max(minimum, min(maximum, value))


def _float(env: Mapping[str, str], key: str, default: float, minimum: float, maximum: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = float(raw)
        except ValueError as exc:
            raise ConfigError(f"{key} must be a number, got {raw!r}") from exc
    return max(minimum, min(maximum, value))


def _enum(env: Mapping[str, str], key: str, default: str, choices: set[str]) -> str:
    value = env.get(key, default).strip().lower()
    if value not in choices:
        expected = ", ".join(sorted(choices))
        raise ConfigError(f"{key} must be one of {expected}; got {value!r}")
    return value


def _path(env: Mapping[str, str], key: str, default: str, *, expand_user: bool = False) -> Path:
    raw = env.get(key, default).strip()
    path = Path(raw)
    return path.expanduser() if expand_user else path


def _load_environment() -> Mapping[str, str]:
    loaded = dict(os.environ)
    env_path = Path(".env")
    if not env_path.exists():
        return loaded
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in loaded:
            continue
        loaded[key] = _parse_env_value(value.strip())
    return loaded


def _parse_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
