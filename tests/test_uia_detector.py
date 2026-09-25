from __future__ import annotations

from pathlib import Path

from qq_autoreply.automation.uia_chat import UiaChatMessage, UiaHeader
from qq_autoreply.config import AppSettings
from qq_autoreply.domain import EventKind, QQWindowInfo, WindowRect
from qq_autoreply.vision.uia_detector import UiaMessageDetector
from qq_autoreply.vision.windows import FakeWindowProvider


class FakeReader:
    def __init__(self) -> None:
        self.window = None
        self.header = UiaHeader("张三")
        self.messages: list[UiaChatMessage] = []

    def bind(self, window: QQWindowInfo) -> None:
        self.window = window

    def read_header(self) -> UiaHeader:
        return self.header

    def read_messages(self) -> list[UiaChatMessage]:
        return list(self.messages)

    def wait_for_self_message(
        self,
        text: str,
        *,
        timeout_seconds: float = 5.0,
        poll_seconds: float = 0.1,
    ) -> bool:
        del timeout_seconds, poll_seconds
        return any(
            message.role == "assistant" and text in message.text
            for message in self.messages
        )


def message(
    key: str,
    *,
    role: str = "user",
    text: str = "你好",
    kind: EventKind = EventKind.PEER_TEXT,
) -> UiaChatMessage:
    return UiaChatMessage(
        key=key,
        runtime_id=(1, int(key.removeprefix("key-"))),
        role=role,  # type: ignore[arg-type]
        text=text,
        kind=kind,
        confidence=1.0,
        captured_at=1.0,
        top=len(key),
    )


def build_detector(tmp_path: Path) -> tuple[UiaMessageDetector, FakeReader]:
    window = QQWindowInfo(
        handle=1,
        title="QQ",
        rect=WindowRect(0, 0, 1200, 800),
    )
    reader = FakeReader()
    detector = UiaMessageDetector(
        settings=AppSettings(target_user_name="张三"),
        reader=reader,  # type: ignore[arg-type]
        window_provider=FakeWindowProvider([window]),  # type: ignore[arg-type]
    )
    detector.bind(window)
    return detector, reader


def test_uia_detector_baselines_then_detects_peer_message(tmp_path: Path) -> None:
    detector, reader = build_detector(tmp_path)
    reader.messages = [message("key-1")]

    baseline = detector.observe()
    reader.messages.append(message("key-2", text="在忙吗"))
    detected = detector.observe()

    assert baseline.kind == EventKind.NONE
    assert detected.kind == EventKind.PEER_TEXT
    assert detected.event is not None
    assert detected.event.text == "在忙吗"


def test_uia_detector_emits_self_message_without_reply_event(tmp_path: Path) -> None:
    detector, reader = build_detector(tmp_path)
    reader.messages = [message("key-1")]
    detector.observe()

    reader.messages.append(
        message(
            "key-2",
            role="assistant",
            text="我自己发的",
            kind=EventKind.SELF_TEXT,
        )
    )
    detected = detector.observe()

    assert detected.kind == EventKind.SELF_TEXT
    assert detected.event is not None
    assert detected.event.text == "我自己发的"


def test_uia_detector_reports_non_text_event(tmp_path: Path) -> None:
    detector, reader = build_detector(tmp_path)
    reader.messages = [message("key-1")]
    detector.observe()

    reader.messages.append(
        message(
            "key-2",
            text="[图片/表情]",
            kind=EventKind.NON_TEXT,
        )
    )
    detected = detector.observe()

    assert detected.kind == EventKind.NON_TEXT


def test_uia_detector_ignores_older_messages_revealed_by_scrolling(tmp_path: Path) -> None:
    detector, reader = build_detector(tmp_path)
    reader.messages = [message("key-1"), message("key-2"), message("key-3")]
    detector.observe()

    reader.messages = [message("key-2"), message("key-3"), message("key-4")]
    appended = detector.observe()
    reader.messages = [
        message("key-0"),
        message("key-2"),
        message("key-3"),
        message("key-4"),
    ]
    older_revealed = detector.observe()

    assert appended.event is not None
    assert appended.event.text == "你好"
    assert older_revealed.kind == EventKind.NONE


def test_uia_target_validation_uses_header(tmp_path: Path) -> None:
    detector, reader = build_detector(tmp_path)

    assert detector.validate_target() is None
    reader.header = UiaHeader("李四")

    result = detector.validate_target()

    assert result is not None
    assert result.kind == EventKind.TARGET_MISMATCH
