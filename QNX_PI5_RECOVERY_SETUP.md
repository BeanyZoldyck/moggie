# Moggie QNX Pi 5 Recovery Setup

Use this if the current Raspberry Pi 5 dies and we have a fresh same-model Pi 5 with QNX installed. This runbook assumes SSH to the new Pi already works as `qnxuser` and the password is `qnxuser`.

The goal is to get the current Moggie game running with Raspberry Pi Camera Module 3 over QNX CamAPI, HDMI, and Pygame.

## 0. Source Of Truth

Important local files on the laptop:

- `/home/mason/Moggie/actual-game` - current game source
- `/home/mason/Moggie/HANDOFF_QNX_CAMERA.md` - detailed camera investigation and fix
- `/home/mason/Moggie/actual-game/native/moggi_camgrab.c` - native QNX CamAPI grabber
- `/home/mason/Moggie/actual-game/app/services/qnx_camera_backend.py` - Python camera backend
- `/home/mason/Moggie/actual-game/run_qnx_hdmi.sh` - kiosk launch script
- `/home/mason/Moggie/actual-game/config_presets/qnx_camera.env` - QNX camera env defaults

Before relying on GitHub alone, check for uncommitted local changes:

```sh
cd /home/mason/Moggie/actual-game
git status --short --branch
```

If there are local changes, copy the local folder to the Pi instead of only cloning from GitHub.

## 1. Confirm Basic QNX Access

From the laptop or WSL helper, confirm:

```sh
ssh qnxuser@qnxpi32.local 'uname -a; id; pwd'
```

From WSL, direct SSH may not route to the Pi. Use Windows `ssh.exe` or recreate the helper from `HANDOFF_QNX_CAMERA.md`:

```sh
/home/mason/qx.sh 'uname -a; id; pwd'
```

If the Pi IP changed, discover it from Windows:

```powershell
Resolve-DnsName qnxpi32.local
```

Then run with:

```sh
QNX_HOST=192.168.137.X /home/mason/qx.sh 'uname -a'
```

## 2. Install QNX Camera Packages

Run on the Pi:

```sh
echo qnxuser | sudo -S apk add \
  yaml \
  libturbojpeg \
  qnx-egl \
  qnx-gles \
  qnx-screen \
  qnx-devu-hcd-dwc3-xhci \
  qnx-sensor-framework-rpi-camera-ipa \
  qnx-io-usb-otg \
  qnx-usb \
  qnx-multimedia-framework \
  qnx-sensor-framework \
  qnx-sensor-framework-camera-imx708 \
  qnx-sensor-framework-rpi5 \
  qnx-sensor-framework-utils
```

Do not hand-copy random `libcamapi` or `libsensor` files. The camera previously broke because the sensor service and libraries were version-mismatched. Use `apk add` so the package set stays consistent.

## 3. Persist The Camera Service Startup

Edit the real startup file:

```sh
echo qnxuser | sudo -S cp /usr/etc/startup/post_startup.sh /usr/etc/startup/post_startup.sh.bak-moggi-recovery
echo qnxuser | sudo -S vi /usr/etc/startup/post_startup.sh
```

The active camera sensor line must be:

```sh
sensor -U 521:521 -b external -r /data/share/sensor -c /system/etc/config/sensor/rpi5_camera_module3.conf
```

Comment out any old generic sensor line that uses `sensor_demo.conf`.

Reboot after editing:

```sh
echo qnxuser | sudo -S shutdown
```

After reboot, verify camera nodes:

```sh
ls /dev/sensor
```

Expected:

```text
camera1
data1
data2
```

If missing, manually restart the service:

```sh
echo qnxuser | sudo -S slay -f sensor
sleep 2
echo qnxuser | sudo -S sensor -U 521:521 -b external -r /data/share/sensor -c /system/etc/config/sensor/rpi5_camera_module3.conf &
sleep 5
ls /dev/sensor
```

## 4. Deploy Game Source

Preferred fast path from the laptop:

```sh
cd /home/mason/Moggie
tar czf /tmp/moggie-actual-game.tgz actual-game HANDOFF_QNX_CAMERA.md QNX_PI5_RECOVERY_SETUP.md
scp /tmp/moggie-actual-game.tgz qnxuser@qnxpi32.local:/data/home/qnxuser/
```

On the Pi:

```sh
cd /data/home/qnxuser
rm -rf moggi-qnx
mkdir -p moggi-qnx
tar xzf moggie-actual-game.tgz -C moggi-qnx
```

Final layout should be:

```text
/data/home/qnxuser/moggi-qnx/actual-game
/data/home/qnxuser/moggi-qnx/HANDOFF_QNX_CAMERA.md
```

If copying through the WSL helper, use `/home/mason/qpush.sh` for small files or Windows `scp.exe` for the tarball.

## 5. Build Native Camera Grabber

Run on the Pi:

```sh
cd /data/home/qnxuser/moggi-qnx/actual-game
gcc native/moggi_camgrab.c -o moggi_camgrab -lcamapi
./moggi_camgrab
```

Expected diagnostic includes successful camera calls and frame info:

```text
camera_open=0
get_vf_property=0
start_viewfinder=0
```

Stop it with `Ctrl+C`.

## 6. Python Environment

Create the venv one directory above `actual-game`, because `run_qnx_hdmi.sh` looks for `../.venv` in the deployed QNX layout:

```sh
cd /data/home/qnxuser/moggi-qnx
python3 -m venv .venv
source .venv/bin/activate
cd actual-game
python -m pip install -e .
```

If QNX already has system Python packages installed and pip install is unnecessary or flaky, at minimum verify these imports:

```sh
cd /data/home/qnxuser/moggi-qnx/actual-game
source ../.venv/bin/activate
python - <<'PY'
import cv2
import numpy
import pygame
from app.services.qnx_camera_backend import QnxCamera
print("cv2", cv2.__version__)
print("numpy", numpy.__version__)
print("pygame", pygame.version.ver)
print("QnxCamera import OK")
PY
```

If MediaPipe causes protobuf or sounddevice issues on QNX, keep the current launcher defaults:

```sh
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
MOGGIE_HAND_TRACKING_BACKEND=simple
MOGGIE_FACE_TRACKING_BACKEND=mediapipe
```

For camera-only emergency testing, disable cloud features:

```sh
MOGGIE_ENABLE_IMAGE_GENERATION=false
MOGGIE_ENABLE_PIKA=false
MOGGIE_ENABLE_LLM_LABELS=false
MOGGIE_EMOJI_USE_CLOUD_VALIDATION=false
```

These are already set by `run_qnx_hdmi.sh`.

## 7. Headless Smoke Test

Run over SSH:

```sh
cd /data/home/qnxuser/moggi-qnx/actual-game
source ../.venv/bin/activate
MOGGIE_CAMERA_BACKEND=qnx SDL_VIDEODRIVER=dummy ./run_qnx_hdmi.sh --frames 60
```

This proves imports, app startup, and the QNX camera backend without taking over HDMI.

## 8. Launch On HDMI

The real Pygame display must run on the Pi HDMI console, not as a remote GUI.

From the Pi keyboard/monitor terminal:

```sh
cd /data/home/qnxuser/moggi-qnx/actual-game
./run_qnx_hdmi.sh
```

If launching via SSH previously worked in this environment, run:

```sh
cd /data/home/qnxuser/moggi-qnx/actual-game
./run_qnx_hdmi.sh
```

The launcher sets:

```text
MOGGIE_CAMERA_BACKEND=qnx
MOGGIE_TARGET_FPS=60
MOGGIE_QNX_CAMERA_GRABBER=./moggi_camgrab
MOGGIE_QNX_CAMERA_UNIT=1
MOGGIE_QNX_CAMERA_DECIMATE=3
MOGGIE_CAMERA_GAIN=2.25
MOGGIE_CAMERA_BRIGHTNESS=42
MOGGIE_HAND_TRACKING_BACKEND=simple
MOGGIE_CV_ENABLE_FACE_DETECTION=true
MOGGIE_FACE_TRACKING_BACKEND=mediapipe
MOGGIE_ENABLE_PIKA=false
MOGGIE_ENABLE_IMAGE_GENERATION=false
```

## 9. Fast Validation Checklist

Run these before handing the kiosk back:

```sh
ls /dev/sensor
cd /data/home/qnxuser/moggi-qnx/actual-game
./moggi_camgrab
source ../.venv/bin/activate
python -m py_compile app/main.py app/services/qnx_camera_backend.py app/ui/screens/mog_mirror_screen.py app/ui/screens/sixty_seven_screen.py
SDL_VIDEODRIVER=dummy ./run_qnx_hdmi.sh --frames 60
```

Acceptance:

- `/dev/sensor/camera1` exists
- `moggi_camgrab` prints frames
- Python imports compile
- dummy SDL startup exits cleanly
- HDMI launch shows the game
- 67 Challenge sees motion
- Mog Mirror sees faces and scores locally
- Cloud/avatar/Pika are disabled for testing

## 10. If It Breaks

Common failures:

- `No module named app.util.video_playback`: use current local `actual-game`; Mog Avatar/Pika is disabled for testing and this import is guarded locally.
- `cannot import MOG_AVATAR_NEGATIVE_PROMPT`: use current local `actual-game`; the testing build removed that hard import.
- No `/dev/sensor/camera1`: camera service is not running or startup config is wrong.
- CamAPI returns `ENOTTY`: package versions are mismatched or sensor was not started with `-b external` and `rpi5_camera_module3.conf`.
- Pygame opens blank over SSH: run on HDMI console or use the exact known QNX/Screen environment from the existing Pi.

When in doubt, read `/data/home/qnxuser/moggi-qnx/HANDOFF_QNX_CAMERA.md`; it contains the deeper camera debugging history.
