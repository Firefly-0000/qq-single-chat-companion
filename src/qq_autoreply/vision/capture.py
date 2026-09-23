from __future__ import annotations

import numpy as np

from ..domain import WindowRect


class CaptureError(RuntimeError):
    pass


class MssCapture:
    def capture(self, region: WindowRect) -> np.ndarray:
        if region.width <= 0 or region.height <= 0:
            raise CaptureError(f"Invalid capture region: {region}")

        import mss

        monitor = {
            "left": region.left,
            "top": region.top,
            "width": region.width,
            "height": region.height,
        }
        try:
            with mss.mss() as capture:
                frame = np.asarray(capture.grab(monitor), dtype=np.uint8)
        except Exception as exc:
            raise CaptureError(f"Screen capture failed: {exc}") from exc
        return frame[:, :, :3]


class FakeCapture:
    def __init__(self, frames: list[np.ndarray]) -> None:
        self.frames = frames
        self.index = 0

    def capture(self, region: WindowRect) -> np.ndarray:
        if not self.frames:
            raise CaptureError("No fake frames configured")
        frame = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return frame
