from __future__ import annotations

from pathlib import Path

from qq_autoreply.domain import ChatMessage, EventKind, EventStatus
from qq_autoreply.storage import Storage


def test_messages_are_persisted_in_order(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "state.sqlite3")
    storage.add_message(
        ChatMessage(role="user", text="第一条", source="ocr", timestamp=1.0)
    )
    storage.add_message(
        ChatMessage(role="assistant", text="第二条", source="deepseek", timestamp=2.0)
    )

    messages = storage.recent_messages(10)

    assert [message.text for message in messages] == ["第一条", "第二条"]
    storage.clear_messages()
    assert storage.recent_messages(10) == []


def test_event_fingerprint_is_idempotent(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "state.sqlite3")
    event = storage.new_event(
        event_id="event-1",
        kind=EventKind.PEER_TEXT,
        fingerprint="same-fingerprint",
        text="你好",
        confidence=0.99,
    )

    assert storage.record_event(event, EventStatus.DETECTED) is True
    assert storage.record_event(event, EventStatus.SENT) is False
    assert storage.event_exists("same-fingerprint") is True
    storage.clear_events()
    assert storage.event_exists("same-fingerprint") is False


def test_runtime_state_round_trip(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "state.sqlite3")
    storage.set_state("last_event", "42")

    assert storage.get_state("last_event") == "42"
    assert storage.get_state("missing", "default") == "default"


def test_replace_messages(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "state.sqlite3")
    storage.add_message(
        ChatMessage(role="user", text="旧消息", source="ocr", timestamp=1.0)
    )
    storage.replace_messages(
        [
            ChatMessage(role="user", text="新消息", source="manual", timestamp=2.0),
            ChatMessage(
                role="assistant",
                text="新回复",
                source="manual",
                timestamp=3.0,
            ),
        ]
    )

    assert [message.text for message in storage.recent_messages(10)] == [
        "新消息",
        "新回复",
    ]
