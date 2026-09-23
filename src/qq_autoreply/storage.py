from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .domain import ChatMessage, EventKind, EventStatus, MessageEvent


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL,
                    timestamp REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    captured_at REAL NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runtime_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def add_message(self, message: ChatMessage) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO messages(role, text, source, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message.role,
                    message.text,
                    message.source,
                    message.confidence,
                    message.timestamp,
                ),
            )

    def recent_messages(self, limit: int) -> list[ChatMessage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, text, source, confidence, timestamp
                FROM messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            ChatMessage(
                role=row["role"],
                text=row["text"],
                source=row["source"],
                confidence=row["confidence"],
                timestamp=row["timestamp"],
            )
            for row in reversed(rows)
        ]

    def clear_messages(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM messages")

    def clear_events(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM events")

    def replace_messages(self, messages: list[ChatMessage]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM messages")
            connection.executemany(
                """
                INSERT INTO messages(role, text, source, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        message.role,
                        message.text,
                        message.source,
                        message.confidence,
                        message.timestamp,
                    )
                    for message in messages
                ],
            )

    def record_event(self, event: MessageEvent, status: EventStatus) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO events(
                    event_id, fingerprint, kind, text, confidence, captured_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.fingerprint,
                    event.kind.value,
                    event.text,
                    event.confidence,
                    event.captured_at,
                    status.value,
                ),
            )
        return cursor.rowcount == 1

    def event_exists(self, fingerprint: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM events WHERE fingerprint = ? LIMIT 1",
                (fingerprint,),
            ).fetchone()
        return row is not None

    def update_event_status(self, event_id: str, status: EventStatus) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE events SET status = ? WHERE event_id = ?",
                (status.value, event_id),
            )

    def set_state(self, key: str, value: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_state(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )

    def get_state(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM runtime_state WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else default

    def new_event(
        self,
        *,
        event_id: str,
        kind: EventKind,
        fingerprint: str,
        text: str,
        confidence: float,
    ) -> MessageEvent:
        return MessageEvent(
            event_id=event_id,
            kind=kind,
            fingerprint=fingerprint,
            text=text,
            confidence=confidence,
            captured_at=time.time(),
        )
