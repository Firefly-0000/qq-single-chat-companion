from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from ..domain import QQWindowInfo, WindowRect


class LayoutProfile(BaseModel):
    sidebar_width_ratio: float = Field(default=0.27, ge=0.1, le=0.6)
    header_height_ratio: float = Field(default=0.11, ge=0.03, le=0.3)
    messages_top_ratio: float = Field(default=0.10, ge=0.03, le=0.4)
    messages_bottom_ratio: float = Field(default=0.79, ge=0.4, le=0.95)
    input_top_ratio: float = Field(default=0.80, ge=0.4, le=0.98)
    input_bottom_ratio: float = Field(default=0.97, ge=0.5, le=0.999)
    peer_side_ratio: float = Field(default=0.62, ge=0.3, le=0.75)


@dataclass(frozen=True, slots=True)
class QQChatLayout:
    window: WindowRect
    header: WindowRect
    messages: WindowRect
    input: WindowRect
    input_click: tuple[int, int]


def _scaled_rect(window: WindowRect, x1: float, y1: float, x2: float, y2: float) -> WindowRect:
    return WindowRect(
        left=window.left + int(window.width * x1),
        top=window.top + int(window.height * y1),
        right=window.left + int(window.width * x2),
        bottom=window.top + int(window.height * y2),
    )


def build_layout(window_info: QQWindowInfo, profile: LayoutProfile) -> QQChatLayout:
    window = window_info.rect
    chat_left = profile.sidebar_width_ratio
    header = _scaled_rect(window, chat_left, 0.0, 1.0, profile.header_height_ratio)
    messages = _scaled_rect(
        window,
        chat_left,
        profile.messages_top_ratio,
        1.0,
        profile.messages_bottom_ratio,
    )
    input_rect = _scaled_rect(
        window,
        chat_left,
        profile.input_top_ratio,
        1.0,
        profile.input_bottom_ratio,
    )
    input_click = (
        input_rect.left + int(input_rect.width * 0.55),
        input_rect.top + int(input_rect.height * 0.55),
    )
    return QQChatLayout(
        window=window,
        header=header,
        messages=messages,
        input=input_rect,
        input_click=input_click,
    )
