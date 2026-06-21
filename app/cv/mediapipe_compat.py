from __future__ import annotations

import sys
import types
import os
from typing import Any


def _configure_qnx_protobuf() -> None:
    if not sys.platform.startswith("qnx"):
        return
    os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")


def _install_qnx_sounddevice_stub() -> None:
    if not sys.platform.startswith("qnx"):
        return
    if "sounddevice" in sys.modules:
        return

    stub = types.ModuleType("sounddevice")

    class PortAudioError(Exception):
        pass

    def query_devices(*args: Any, **kwargs: Any) -> list[Any]:
        return []

    stub.PortAudioError = PortAudioError
    stub.query_devices = query_devices
    sys.modules["sounddevice"] = stub


def import_mediapipe() -> Any:
    _configure_qnx_protobuf()
    _install_qnx_sounddevice_stub()
    import mediapipe as mp

    return mp
