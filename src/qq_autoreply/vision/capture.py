from __future__ import annotations

import numpy as np

from ..domain import WindowRect


class CaptureError(RuntimeError):
    pass


class MssCapture:
    def __init__(self) -> None:
        self.window_handle: int | None = None
        self.last_backend = ""

    def capture(self, region: WindowRect) -> np.ndarray:
        if region.width <= 0 or region.height <= 0:
            raise CaptureError(f"Invalid capture region: {region}")

        errors: list[str] = []
        for backend_name, backend in (
            ("mss", self._capture_mss),
            ("printwindow", self._capture_printwindow),
            ("imagegrab", self._capture_imagegrab),
        ):
            try:
                frame = backend(region)
            except Exception as exc:
                errors.append(f"{backend_name}: {exc}")
                continue
            self.last_backend = backend_name
            return frame
        raise CaptureError("Screen capture failed; " + "; ".join(errors))

    @staticmethod
    def _capture_mss(region: WindowRect) -> np.ndarray:
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
            raise CaptureError(str(exc)) from exc
        return frame[:, :, :3]

    def _capture_printwindow(self, region: WindowRect) -> np.ndarray:
        if self.window_handle is None:
            raise CaptureError("window handle is not configured")

        import win32gui
        import win32ui

        handle = self.window_handle
        if not win32gui.IsWindow(handle):
            raise CaptureError("window handle no longer exists")
        window_left, window_top, window_right, window_bottom = win32gui.GetWindowRect(
            handle
        )
        width = window_right - window_left
        height = window_bottom - window_top
        if width <= 0 or height <= 0:
            raise CaptureError("window has an invalid size")

        window_dc = win32gui.GetWindowDC(handle)
        source_dc = win32ui.CreateDCFromHandle(window_dc)
        memory_dc = source_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(source_dc, width, height)
            memory_dc.SelectObject(bitmap)
            rendered = win32gui.PrintWindow(handle, memory_dc.GetSafeHdc(), 2)
            if not rendered:
                raise CaptureError("PrintWindow returned failure")
            raw = bitmap.GetBitmapBits(True)
            image = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
        finally:
            win32gui.DeleteObject(bitmap.GetHandle())
            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            win32gui.ReleaseDC(handle, window_dc)

        relative_left = region.left - window_left
        relative_top = region.top - window_top
        relative_right = relative_left + region.width
        relative_bottom = relative_top + region.height
        if (
            relative_left < 0
            or relative_top < 0
            or relative_right > width
            or relative_bottom > height
        ):
            raise CaptureError("requested region is outside the captured window")
        return image[
            relative_top:relative_bottom,
            relative_left:relative_right,
            :3,
        ].copy()

    @staticmethod
    def _capture_imagegrab(region: WindowRect) -> np.ndarray:
        from PIL import ImageGrab

        image = ImageGrab.grab(
            bbox=(region.left, region.top, region.right, region.bottom),
            all_screens=True,
        )
        return np.asarray(image, dtype=np.uint8)[:, :, ::-1].copy()


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
