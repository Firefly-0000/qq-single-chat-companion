from __future__ import annotations

from typing import Protocol

from .domain import ChatMessage, DetectionResult, QQWindowInfo, WindowRect


class DetectorPort(Protocol):
    def bind(self, window: QQWindowInfo) -> None: ...

    def observe(self) -> DetectionResult: ...


class ReplyGeneratorPort(Protocol):
    def generate(self, messages: list[ChatMessage]) -> str: ...


class ReplySenderPort(Protocol):
    def send(self, text: str) -> None: ...


class WindowProviderPort(Protocol):
    def list_windows(self) -> list[QQWindowInfo]: ...

    def get_rect(self, handle: int) -> WindowRect: ...

    def focus(self, handle: int) -> None: ...
