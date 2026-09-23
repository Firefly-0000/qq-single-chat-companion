from __future__ import annotations

import time
from pathlib import Path

from qq_autoreply.automation.input import FakeReplySender
from qq_autoreply.config import AppSettings
from qq_autoreply.domain import (
    BotState,
    DetectionResult,
    EventKind,
    MessageEvent,
    QQWindowInfo,
    SendDeferredError,
    WindowRect,
)
from qq_autoreply.service.orchestrator import Orchestrator
from qq_autoreply.storage import Storage


class FakeDetector:
    def __init__(self, result: DetectionResult) -> None:
        self.result = result
        self.bound = None

    def bind(self, window: QQWindowInfo) -> None:
        self.bound = window

    def observe(self) -> DetectionResult:
        return self.result


class FakeGenerator:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def generate(self, messages: object) -> str:
        self.calls += 1
        return self.reply


class DeferredSender:
    def __init__(self) -> None:
        self.calls = 0
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.calls += 1
        if self.calls == 1:
            raise SendDeferredError("user is typing")
        self.sent.append(text)


def event(
    fingerprint: str = "fp-1",
    text: str = "你好",
    event_id: str = "event-1",
) -> MessageEvent:
    return MessageEvent(
        event_id=event_id,
        kind=EventKind.PEER_TEXT,
        fingerprint=fingerprint,
        text=text,
        confidence=0.99,
        captured_at=1.0,
    )


def build_orchestrator(
    tmp_path: Path,
    *,
    auto_send: bool,
    reply: str = "我挺好的，你呢？",
) -> tuple[Orchestrator, Storage, FakeGenerator, FakeReplySender]:
    settings = AppSettings(
        target_user_name="张三",
        auto_send=auto_send,
        batch_window_ms=0,
    )
    storage = Storage(tmp_path / "state.sqlite3")
    detector = FakeDetector(
        DetectionResult(kind=EventKind.PEER_TEXT, event=event())
    )
    generator = FakeGenerator(reply)
    sender = FakeReplySender()
    orchestrator = Orchestrator(
        settings=settings,
        storage=storage,
        detector=detector,
        generator=generator,
        sender=sender,
    )
    orchestrator.bind(
        QQWindowInfo(handle=1, title="QQ", rect=WindowRect(0, 0, 1200, 800))
    )
    orchestrator.start()
    return orchestrator, storage, generator, sender


def test_draft_mode_does_not_send(tmp_path: Path) -> None:
    orchestrator, storage, generator, sender = build_orchestrator(
        tmp_path, auto_send=False
    )

    result = orchestrator.tick()

    assert result.reply == "我挺好的，你呢？"
    assert sender.sent == []
    assert generator.calls == 1
    assert [message.role for message in storage.recent_messages(10)] == [
        "user",
        "assistant",
    ]


def test_auto_send_mode_sends_once(tmp_path: Path) -> None:
    orchestrator, _, generator, sender = build_orchestrator(tmp_path, auto_send=True)

    first = orchestrator.tick()
    second = orchestrator.tick()

    assert first.message == "reply sent"
    assert second.message == "duplicate event"
    assert sender.sent == ["我挺好的，你呢？"]
    assert generator.calls == 1


def test_forbidden_topic_pauses(tmp_path: Path) -> None:
    orchestrator, _, _, sender = build_orchestrator(
        tmp_path,
        auto_send=True,
        reply="请把验证码发给我",
    )

    result = orchestrator.tick()

    assert result.state == BotState.PAUSED
    assert sender.sent == []


def test_messages_are_batched_before_generation(tmp_path: Path) -> None:
    settings = AppSettings(
        target_user_name="张三",
        auto_send=True,
        batch_window_ms=50,
    )
    storage = Storage(tmp_path / "state.sqlite3")
    first_event = event("fp-1", "第一句")
    second_event = event("fp-2", "第二句")
    detector = FakeDetector(
        DetectionResult(kind=EventKind.PEER_TEXT, event=first_event)
    )
    generator = FakeGenerator("合并回复")
    sender = FakeReplySender()
    orchestrator = Orchestrator(
        settings=settings,
        storage=storage,
        detector=detector,
        generator=generator,
        sender=sender,
    )
    orchestrator.bind(
        QQWindowInfo(handle=1, title="QQ", rect=WindowRect(0, 0, 1200, 800))
    )
    orchestrator.start()

    queued = orchestrator.tick()
    detector.result = DetectionResult(kind=EventKind.PEER_TEXT, event=second_event)
    time.sleep(0.02)
    second_queued = orchestrator.tick()
    time.sleep(0.06)
    completed = orchestrator.tick()

    assert queued.message == "message queued for batching"
    assert second_queued.message == "message queued for batching"
    assert completed.message == "reply sent"
    assert generator.calls == 1
    assert sender.sent == ["合并回复"]


def test_100_round_soak_simulation(tmp_path: Path) -> None:
    settings = AppSettings(
        target_user_name="张三",
        auto_send=True,
        batch_window_ms=0,
        context_recent_messages=20,
    )
    storage = Storage(tmp_path / "state.sqlite3")
    detector = FakeDetector(
        DetectionResult(kind=EventKind.PEER_TEXT, event=event())
    )
    generator = FakeGenerator("收到")
    sender = FakeReplySender()
    orchestrator = Orchestrator(
        settings=settings,
        storage=storage,
        detector=detector,
        generator=generator,
        sender=sender,
    )
    orchestrator.bind(
        QQWindowInfo(handle=1, title="QQ", rect=WindowRect(0, 0, 1200, 800))
    )
    orchestrator.start()

    for index in range(100):
        detector.result = DetectionResult(
            kind=EventKind.PEER_TEXT,
            event=event(
                fingerprint=f"fp-{index}",
                text=f"消息{index}",
                event_id=f"event-{index}",
            ),
        )
        result = orchestrator.tick()
        assert result.message == "reply sent"

    assert generator.calls == 100
    assert sender.sent == ["收到"] * 100
    assert len(storage.recent_messages(500)) == 200


def test_send_is_deferred_until_next_tick_when_user_is_active(tmp_path: Path) -> None:
    settings = AppSettings(
        target_user_name="张三",
        auto_send=True,
        batch_window_ms=0,
    )
    storage = Storage(tmp_path / "state.sqlite3")
    detector = FakeDetector(
        DetectionResult(kind=EventKind.PEER_TEXT, event=event())
    )
    generator = FakeGenerator("稍后发送")
    sender = DeferredSender()
    orchestrator = Orchestrator(
        settings=settings,
        storage=storage,
        detector=detector,
        generator=generator,
        sender=sender,
    )
    orchestrator.bind(
        QQWindowInfo(handle=1, title="QQ", rect=WindowRect(0, 0, 1200, 800))
    )
    orchestrator.start()

    deferred = orchestrator.tick()
    completed = orchestrator.tick()

    assert deferred.message == "user is typing"
    assert completed.message == "deferred reply sent"
    assert sender.sent == ["稍后发送"]
    assert generator.calls == 1
