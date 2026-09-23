from __future__ import annotations

import logging
import time
import warnings

from ..config import AppSettings
from ..domain import WindowRect
from ..vision.capture import MssCapture
from ..vision.detector import MessageDetector, normalize_text
from ..vision.ocr import RapidOcrEngine
from ..vision.windows import Win32WindowProvider

logger = logging.getLogger(__name__)


class SendError(RuntimeError):
    pass


class InputVerificationError(SendError):
    pass


class SendUncertainError(SendError):
    pass


class UIAutomationError(SendError):
    pass


def _select_edit_control(controls: list[object]) -> object:
    candidates = [
        control
        for control in controls
        if getattr(control.element_info, "control_type", "") == "Edit"
        and control.is_visible()
        and control.is_enabled()
    ]
    if not candidates:
        raise UIAutomationError("QQ input Edit control was not found")
    return max(candidates, key=lambda control: control.rectangle().width())


def _select_send_button(controls: list[object]) -> object:
    candidates = [
        control
        for control in controls
        if getattr(control.element_info, "control_type", "") == "Button"
        and "send" in str(getattr(control.element_info, "class_name", "")).casefold()
        and control.is_visible()
        and control.is_enabled()
    ]
    if not candidates:
        raise UIAutomationError("QQ send button was not found")
    return candidates[0]


class DesktopReplySender:
    def __init__(
        self,
        *,
        settings: AppSettings,
        detector: MessageDetector,
        capture: MssCapture,
        ocr: RapidOcrEngine,
        window_provider: Win32WindowProvider,
    ) -> None:
        self.settings = settings
        self.detector = detector
        self.capture = capture
        self.ocr = ocr
        self.window_provider = window_provider

    def send(self, text: str) -> None:
        if self.detector.window is None or self.detector.layout is None:
            raise SendError("No bound QQ window")
        if not text.strip():
            raise SendError("Refusing to send empty text")

        validation = self.detector.validate_target()
        if validation is not None:
            raise SendError(validation.reason or "Target validation failed")

        layout = self.detector.layout
        try:
            self._send_via_uia(text)
        except SendError:
            raise
        except Exception as exc:
            raise UIAutomationError(f"UI Automation send failed: {exc}") from exc

        if not self._verify_sent(text, layout.messages):
            raise SendUncertainError("Could not confirm outgoing message")

    def _send_via_uia(self, text: str) -> None:
        if self.detector.window is None:
            raise UIAutomationError("No bound QQ window")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning, module="pywinauto")
            from pywinauto import Desktop

        window = Desktop(backend="uia").window(handle=self.detector.window.handle)
        controls = list(window.descendants())
        edit = _select_edit_control(controls)
        edit.iface_value.SetValue(text)
        observed = str(edit.iface_value.CurrentValue)
        if normalize_text(observed) != normalize_text(text):
            raise InputVerificationError("UI Automation input verification failed")

        controls = list(window.descendants())
        send_button = _select_send_button(controls)
        send_button.iface_invoke.Invoke()
        time.sleep(0.2)

    def _verify_sent(self, text: str, message_rect: WindowRect) -> bool:
        expected = normalize_text(text)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            frame = self.capture.capture(message_rect)
            lines = self.ocr.recognize(frame)
            for line in lines:
                if line.center_x < message_rect.width * 0.55:
                    continue
                observed = normalize_text(line.text)
                if expected and (expected in observed or observed in expected):
                    return True
            time.sleep(0.25)
        return False


class FakeReplySender:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)
