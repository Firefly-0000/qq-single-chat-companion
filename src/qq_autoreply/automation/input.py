from __future__ import annotations

import logging
import time
import warnings
from typing import Any

from ..config import AppSettings
from ..domain import SendDeferredError
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


def _get_clipboard_text() -> str:
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(
            win32clipboard.CF_UNICODETEXT
        ):
            return str(win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT))
        return ""
    finally:
        win32clipboard.CloseClipboard()


def _set_clipboard_text(text: str) -> None:
    import win32clipboard

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def _select_chat_input(controls: list[object]) -> object:
    candidates = [
        control
        for control in controls
        if getattr(control.element_info, "control_type", "") in {"Group", "Edit"}
        and "ExEditor-qq-msg-editor"
        in str(getattr(control.element_info, "class_name", ""))
        and control.is_visible()
        and control.is_enabled()
    ]
    if not candidates:
        raise UIAutomationError("QQ chat input control was not found")
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
        detector: Any,
        window_provider: Win32WindowProvider,
    ) -> None:
        self.settings = settings
        self.detector = detector
        self.window_provider = window_provider

    def send(self, text: str) -> None:
        self._write_chat_input(text)
        self._invoke_send()
        if not self.detector.wait_for_self_message(text):
            raise SendUncertainError("Could not confirm outgoing message")

    def fill(self, text: str) -> None:
        self._write_chat_input(text)

    def _write_chat_input(self, text: str) -> None:
        if self.detector.window is None or self.detector.layout is None:
            raise UIAutomationError("No bound QQ window")
        if not text.strip():
            raise SendError("Refusing to write empty text")
        validation = self.detector.validate_target()
        if validation is not None:
            raise SendError(validation.reason or "Target validation failed")
        idle_seconds = self.window_provider.idle_seconds()
        if idle_seconds < self.settings.focus_guard_idle_seconds:
            raise SendDeferredError(
                f"user input active ({idle_seconds:.2f}s idle); send deferred"
            )

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning, module="pywinauto")
            from pywinauto import Desktop, keyboard

        window = Desktop(backend="uia").window(handle=self.detector.window.handle)
        controls = list(window.descendants())
        chat_input = _select_chat_input(controls)
        if "is-empty" not in str(chat_input.element_info.class_name):
            raise SendDeferredError("QQ chat input already contains text")
        previous_foreground = self.window_provider.foreground_handle()
        previous_clipboard = _get_clipboard_text()
        try:
            self.window_provider.focus(self.detector.window.handle)
            chat_input.set_focus()
            _set_clipboard_text(text)
            keyboard.send_keys("^a")
            keyboard.send_keys("^v")
            time.sleep(0.2)
            controls = list(window.descendants())
            updated_input = _select_chat_input(controls)
            if "is-empty" in str(updated_input.element_info.class_name):
                raise InputVerificationError("Chat input verification failed")
        finally:
            try:
                _set_clipboard_text(previous_clipboard)
            except Exception:
                logger.debug("Clipboard restore failed", exc_info=True)
            if previous_foreground != self.detector.window.handle:
                try:
                    self.window_provider.focus(previous_foreground)
                except Exception:
                    logger.debug("Foreground restore failed", exc_info=True)

    def _invoke_send(self) -> None:
        if self.detector.window is None:
            raise UIAutomationError("No bound QQ window")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning, module="pywinauto")
            from pywinauto import Desktop

        window = Desktop(backend="uia").window(handle=self.detector.window.handle)
        last_error: Exception | None = None
        for _ in range(10):
            controls = list(window.descendants())
            try:
                send_button = _select_send_button(controls)
            except UIAutomationError as exc:
                last_error = exc
                time.sleep(0.1)
                continue
            send_button.iface_invoke.Invoke()
            time.sleep(0.2)
            return
        raise UIAutomationError(str(last_error or "QQ send button was not found"))

class FakeReplySender:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.drafted: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)

    def fill(self, text: str) -> None:
        self.drafted.append(text)
