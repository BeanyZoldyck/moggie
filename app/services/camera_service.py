from __future__ import annotations


class CameraService:
    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass
