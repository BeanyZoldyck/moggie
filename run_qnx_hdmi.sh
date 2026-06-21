#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f "../.venv/bin/activate" ]; then
  # Deployed QNX layout: ~/moggi-qnx/actual-game with venv at ~/moggi-qnx/.venv.
  # shellcheck disable=SC1091
  source "../.venv/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
  # Local/repo layout.
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

export MOGGIE_CAMERA_BACKEND="${MOGGIE_CAMERA_BACKEND:-qnx}"
export MOGGIE_TARGET_FPS="${MOGGIE_TARGET_FPS:-60}"
export MOGGIE_QNX_CAMERA_GRABBER="${MOGGIE_QNX_CAMERA_GRABBER:-./moggi_camgrab}"
export MOGGIE_QNX_CAMERA_UNIT="${MOGGIE_QNX_CAMERA_UNIT:-1}"
export MOGGIE_QNX_CAMERA_DECIMATE="${MOGGIE_QNX_CAMERA_DECIMATE:-3}"
export MOGGIE_CAMERA_GAIN="${MOGGIE_CAMERA_GAIN:-2.25}"
export MOGGIE_CAMERA_BRIGHTNESS="${MOGGIE_CAMERA_BRIGHTNESS:-42}"
export MOGGIE_CV_FPS="${MOGGIE_CV_FPS:-30}"
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="${PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION:-python}"
export MOGGIE_HAND_TRACKING_BACKEND="${MOGGIE_HAND_TRACKING_BACKEND:-simple}"
export MOGGIE_CV_ENABLE_FACE_DETECTION="${MOGGIE_CV_ENABLE_FACE_DETECTION:-true}"
export MOGGIE_FACE_TRACKING_BACKEND="${MOGGIE_FACE_TRACKING_BACKEND:-mediapipe}"
export MOGGIE_67_ROUND_SECONDS="${MOGGIE_67_ROUND_SECONDS:-12}"
export MOGGIE_67_MAX_HANDS="${MOGGIE_67_MAX_HANDS:-4}"
export MOGGIE_67_MIN_CONFIDENCE="${MOGGIE_67_MIN_CONFIDENCE:-0.25}"

# Keep local SQLite leaderboards, but force Redis/cloud paths off for the QNX
# kiosk run. Network cache retries can block the post-game transition.
export MOGGIE_ENABLE_REDIS_LEADERBOARD_CACHE=false
export MOGGIE_ENABLE_IMAGE_GENERATION=false
export MOGGIE_ENABLE_MIDJOURNEY=false
export MOGGIE_ENABLE_PIKA=false
export MOGGIE_ENABLE_S3_VIDEO_STORAGE=false
export MOGGIE_SAVE_GENERATED_MEDIA=false
export MOGGIE_ENABLE_LLM_LABELS=false
export MOGGIE_EMOJI_USE_CLOUD_VALIDATION=false
export MOGGIE_ENABLE_VOICE="${MOGGIE_ENABLE_VOICE:-false}"

python -m app.main "$@"
