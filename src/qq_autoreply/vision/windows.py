from __future__ import annotations

import os
import sys
from contextlib import suppress
from pathlib import Path

from ..domain import QQWindowInfo, WindowRect

QQ_PROCESS_NAMES = {
    "qq.exe",
    "qqnt.exe",
    "imqq.exe",
    "qqsc.exe",
}


class WindowAccessError(RuntimeError):
    pass


def is_qq_candidate_window(
    *,
    title: str,
    class_name: str,
    process_name: str,
    process_id: int,
    current_process_id: int,
) -> bool:
    if process_id == current_process_id:
        return False
    if class_name.startswith("Qt") or class_name == "ConsoleWindowClass":
        return False
    if process_name.casefold() not in QQ_PROCESS_NAMES:
        return False
    return bool(title.strip())


class Win32WindowProvider:
    def list_windows(self) -> list[QQWindowInfo]:
        if sys.platform != "win32":
            raise WindowAccessError("QQ window automation is only supported on Windows")

        import win32gui
        import win32process

        current_process_id = os.getpid()

        windows: list[QQWindowInfo] = []

        def collect(handle: int, _: object) -> None:
            if not win32gui.IsWindowVisible(handle):
                return
            title = win32gui.GetWindowText(handle)
            class_name = win32gui.GetClassName(handle)
            _, process_id = win32process.GetWindowThreadProcessId(handle)
            if not is_qq_candidate_window(
                title=title,
                class_name=class_name,
                process_name=self._process_name(process_id),
                process_id=process_id,
                current_process_id=current_process_id,
            ):
                return
            try:
                rect = self.get_rect(handle)
            except WindowAccessError:
                return
            if rect.width < 400 or rect.height < 300:
                return
            windows.append(QQWindowInfo(handle=handle, title=title, rect=rect))

        win32gui.EnumWindows(collect, None)
        return windows

    @staticmethod
    def _process_name(process_id: int) -> str:
        if sys.platform != "win32":
            return ""
        try:
            import win32api
            import win32con
            import win32process

            access = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
            handle = win32api.OpenProcess(access, False, process_id)
            try:
                executable = win32process.GetModuleFileNameEx(handle, 0)
            finally:
                win32api.CloseHandle(handle)
            return Path(executable).name
        except Exception:
            return ""

    def get_rect(self, handle: int) -> WindowRect:
        if sys.platform != "win32":
            raise WindowAccessError("QQ window automation is only supported on Windows")

        import win32gui

        if not win32gui.IsWindow(handle):
            raise WindowAccessError(f"Window handle no longer exists: {handle}")
        left, top, right, bottom = win32gui.GetWindowRect(handle)
        return WindowRect(left=left, top=top, right=right, bottom=bottom)

    def focus(self, handle: int) -> None:
        if sys.platform != "win32":
            raise WindowAccessError("QQ window automation is only supported on Windows")

        import win32con
        import win32gui

        if not win32gui.IsWindow(handle):
            raise WindowAccessError(f"Window handle no longer exists: {handle}")
        if win32gui.IsIconic(handle):
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)
        if win32gui.GetForegroundWindow() == handle:
            return
        with suppress(Exception):
            win32gui.SetForegroundWindow(handle)
        if win32gui.GetForegroundWindow() == handle:
            return
        try:
            win32gui.ShowWindow(handle, win32con.SW_SHOW)
            win32gui.BringWindowToTop(handle)
            win32gui.SetForegroundWindow(handle)
        except Exception:
            pass
        if win32gui.GetForegroundWindow() != handle:
            raise WindowAccessError("Unable to bring the QQ window to the foreground")

    def foreground_handle(self) -> int:
        if sys.platform != "win32":
            raise WindowAccessError("QQ window automation is only supported on Windows")

        import win32gui

        return win32gui.GetForegroundWindow()


class FakeWindowProvider:
    def __init__(self, windows: list[QQWindowInfo]) -> None:
        self.windows = windows
        self.focused: list[int] = []

    def list_windows(self) -> list[QQWindowInfo]:
        return list(self.windows)

    def get_rect(self, handle: int) -> WindowRect:
        for window in self.windows:
            if window.handle == handle:
                return window.rect
        raise WindowAccessError(f"Unknown window: {handle}")

    def focus(self, handle: int) -> None:
        self.focused.append(handle)
