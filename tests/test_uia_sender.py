from __future__ import annotations

import pytest

from qq_autoreply.automation.input import (
    UIAutomationError,
    _select_chat_input,
    _select_send_button,
)


class _Info:
    def __init__(self, control_type: str, class_name: str = "") -> None:
        self.control_type = control_type
        self.class_name = class_name


class _Rect:
    def __init__(self, width: int) -> None:
        self._width = width

    def width(self) -> int:
        return self._width


class _Control:
    def __init__(
        self,
        control_type: str,
        *,
        class_name: str = "",
        width: int = 100,
        visible: bool = True,
        enabled: bool = True,
    ) -> None:
        self.element_info = _Info(control_type, class_name)
        self._width = width
        self._visible = visible
        self._enabled = enabled

    def is_visible(self) -> bool:
        return self._visible

    def is_enabled(self) -> bool:
        return self._enabled

    def rectangle(self) -> _Rect:
        return _Rect(self._width)


def test_select_chat_input_uses_prosemirror_editor() -> None:
    expected = _Control(
        "Group",
        class_name="ProseMirror ExEditor-qq-msg-editor is-empty",
        width=300,
    )
    controls = [
        _Control("Button"),
        _Control("Edit", class_name="search-input", width=50),
        expected,
        _Control("Group", class_name="ExEditor-qq-msg-editor", width=500, visible=False),
    ]

    assert _select_chat_input(controls) is expected


def test_select_send_button_uses_send_class() -> None:
    expected = _Control("Button", class_name="send-msg")
    controls = [_Control("Button", class_name="cancel"), expected]

    assert _select_send_button(controls) is expected


def test_missing_uia_controls_raise() -> None:
    with pytest.raises(UIAutomationError):
        _select_chat_input([])
    with pytest.raises(UIAutomationError):
        _select_send_button([])
