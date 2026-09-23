from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class BotState(StrEnum):
    UNBOUND = "UNBOUND"
    READY = "READY"
    MONITORING = "MONITORING"
    GENERATING = "GENERATING"
    SENDING = "SENDING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class EventKind(StrEnum):
    NONE = "none"
    PEER_TEXT = "peer_text"
    NON_TEXT = "non_text_event"
    TARGET_MISMATCH = "target_mismatch"
    LOW_CONFIDENCE = "low_confidence"
    ERROR = "error"


class EventStatus(StrEnum):
    DETECTED = "DETECTED"
    DRAFTED = "DRAFTED"
    SENT = "SENT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    SEND_UNCERTAIN = "SEND_UNCERTAIN"


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> Point:
        return Point((self.left + self.right) // 2, (self.top + self.bottom) // 2)


@dataclass(frozen=True, slots=True)
class QQWindowInfo:
    handle: int
    title: str
    rect: WindowRect


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True, slots=True)
class MessageEvent:
    event_id: str
    kind: EventKind
    fingerprint: str
    text: str
    confidence: float
    captured_at: float


@dataclass(frozen=True, slots=True)
class DetectionResult:
    kind: EventKind
    event: MessageEvent | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    text: str
    source: str
    timestamp: float
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class TickResult:
    state: BotState
    kind: EventKind
    event: MessageEvent | None = None
    reply: str | None = None
    message: str = ""
    context: list[ChatMessage] = field(default_factory=list)
