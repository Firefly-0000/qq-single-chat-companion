from __future__ import annotations

import numpy as np
import pytest

from qq_autoreply.domain import WindowRect
from qq_autoreply.vision.capture import CaptureError, MssCapture


class FallbackCapture(MssCapture):
    def __init__(
        self,
        *,
        fail_mss: bool = False,
        fail_printwindow: bool = False,
        fail_imagegrab: bool = False,
    ) -> None:
        super().__init__()
        self.fail_mss = fail_mss
        self.fail_printwindow = fail_printwindow
        self.fail_imagegrab = fail_imagegrab

    def _capture_mss(self, region: WindowRect) -> np.ndarray:
        if self.fail_mss:
            raise CaptureError("mss failed")
        return np.full((10, 10, 3), 1, dtype=np.uint8)

    def _capture_printwindow(self, region: WindowRect) -> np.ndarray:
        if self.fail_printwindow:
            raise CaptureError("printwindow failed")
        return np.full((10, 10, 3), 2, dtype=np.uint8)

    def _capture_imagegrab(self, region: WindowRect) -> np.ndarray:
        if self.fail_imagegrab:
            raise CaptureError("imagegrab failed")
        return np.full((10, 10, 3), 3, dtype=np.uint8)


def test_capture_falls_back_to_printwindow() -> None:
    capture = FallbackCapture(fail_mss=True)

    frame = capture.capture(WindowRect(0, 0, 10, 10))

    assert int(frame[0, 0, 0]) == 2
    assert capture.last_backend == "printwindow"


def test_capture_falls_back_to_imagegrab() -> None:
    capture = FallbackCapture(fail_mss=True, fail_printwindow=True)

    frame = capture.capture(WindowRect(0, 0, 10, 10))

    assert int(frame[0, 0, 0]) == 3
    assert capture.last_backend == "imagegrab"


def test_capture_reports_all_backend_failures() -> None:
    capture = FallbackCapture(
        fail_mss=True,
        fail_printwindow=True,
        fail_imagegrab=True,
    )

    with pytest.raises(CaptureError, match="mss.*printwindow.*imagegrab"):
        capture.capture(WindowRect(0, 0, 10, 10))
