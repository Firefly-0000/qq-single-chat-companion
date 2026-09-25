from __future__ import annotations

import time
import uuid
from collections import deque

from ..automation.uia_chat import UiaChatError, UiaChatMessage, UiaChatReader
from ..config import AppSettings
from ..domain import (
    ChatMessage,
    DetectionResult,
    EventKind,
    MessageEvent,
    QQWindowInfo,
)
from ..text import normalize_text
from .windows import Win32WindowProvider


class UiaMessageDetector:
    def __init__(
        self,
        *,
        settings: AppSettings,
        reader: UiaChatReader,
        window_provider: Win32WindowProvider,
    ) -> None:
        self.settings = settings
        self.reader = reader
        self.window_provider = window_provider
        self.window: QQWindowInfo | None = None
        self._last_snapshot: list[UiaChatMessage] = []
        self._pending: deque[UiaChatMessage] = deque()
        self._baseline_ready = False
        self._empty_baseline_since: float | None = None
        self._header_checks = 0
        self._target_mismatch_count = 0

    def bind(self, window: QQWindowInfo) -> None:
        self.window = window
        self.reader.bind(window)
        self._last_snapshot = []
        self._pending.clear()
        self._baseline_ready = False
        self._empty_baseline_since = None
        self._header_checks = 0
        self._target_mismatch_count = 0

    def validate_target(self, *, allow_empty: bool = False) -> DetectionResult | None:
        try:
            header = self.reader.read_header()
        except UiaChatError as exc:
            return DetectionResult(kind=EventKind.ERROR, reason=str(exc))
        if header.group_markers:
            return DetectionResult(
                kind=EventKind.TARGET_MISMATCH,
                reason="Group-chat markers detected in the active conversation header",
            )
        expected = normalize_text(self.settings.target_user_name)
        observed = normalize_text(header.name)
        if not observed and allow_empty:
            return DetectionResult(
                kind=EventKind.NONE,
                reason="target header is not ready",
            )
        if expected and expected not in observed:
            return DetectionResult(
                kind=EventKind.TARGET_MISMATCH,
                reason=(
                    f"Expected target {self.settings.target_user_name!r}, "
                    f"observed {header.name!r}"
                ),
            )
        return None

    def read_visible_history(self, limit: int = 200) -> list[ChatMessage]:
        try:
            messages = self.reader.read_messages()
        except UiaChatError:
            return []
        return [message.to_chat_message() for message in messages[-limit:]]

    def wait_for_self_message(self, text: str, timeout_seconds: float = 5.0) -> bool:
        try:
            return self.reader.wait_for_self_message(
                text,
                timeout_seconds=timeout_seconds,
            )
        except UiaChatError:
            return False

    def observe(self) -> DetectionResult:
        if self.window is None:
            return DetectionResult(kind=EventKind.ERROR, reason="No QQ window is bound")
        try:
            current_rect = self.window_provider.get_rect(self.window.handle)
        except Exception as exc:
            return DetectionResult(kind=EventKind.ERROR, reason=str(exc))
        if current_rect != self.window.rect:
            self.window = QQWindowInfo(
                handle=self.window.handle,
                title=self.window.title,
                rect=current_rect,
            )

        if self._header_checks % 4 == 0 or self._target_mismatch_count > 0:
            validation = self.validate_target(allow_empty=True)
            if validation is not None:
                if validation.kind == EventKind.NONE:
                    self._target_mismatch_count = 0
                    self._header_checks += 1
                    return validation
                if validation.reason.startswith("Group-chat"):
                    self._header_checks += 1
                    return validation
                self._target_mismatch_count += 1
                self._header_checks += 1
                if self._target_mismatch_count >= 2:
                    return validation
                return DetectionResult(
                    kind=EventKind.NONE,
                    reason="target check requires confirmation",
                )
            self._target_mismatch_count = 0
        self._header_checks += 1

        try:
            snapshot = self.reader.read_messages()
        except UiaChatError as exc:
            return DetectionResult(kind=EventKind.ERROR, reason=str(exc))

        if not self._baseline_ready:
            if not snapshot:
                now = time.monotonic()
                if self._empty_baseline_since is None:
                    self._empty_baseline_since = now
                if now - self._empty_baseline_since < 1.5:
                    return DetectionResult(
                        kind=EventKind.NONE,
                        reason="waiting for UIA baseline",
                    )
            self._last_snapshot = snapshot
            self._baseline_ready = True
            self._empty_baseline_since = None
            return DetectionResult(kind=EventKind.NONE, reason="uia baseline captured")

        new_messages = _tail_additions(self._last_snapshot, snapshot)
        self._last_snapshot = snapshot
        self._pending.extend(new_messages)

        if not self._pending:
            return DetectionResult(kind=EventKind.NONE)
        message = self._pending.popleft()
        return DetectionResult(
            kind=message.kind,
            event=MessageEvent(
                event_id=str(uuid.uuid4()),
                kind=message.kind,
                fingerprint=message.key,
                text=message.text,
                confidence=message.confidence,
                captured_at=message.captured_at,
            ),
            reason="uia message detected",
        )


def _tail_additions(
    previous: list[UiaChatMessage],
    current: list[UiaChatMessage],
) -> list[UiaChatMessage]:
    if not current:
        return []
    if not previous:
        return current

    maximum_overlap = 0
    for size in range(1, min(len(previous), len(current)) + 1):
        if [message.key for message in previous[-size:]] == [
            message.key for message in current[:size]
        ]:
            maximum_overlap = size
    if maximum_overlap:
        return current[maximum_overlap:]

    previous_last = previous[-1].key
    for index in range(len(current) - 1, -1, -1):
        if current[index].key == previous_last:
            return current[index + 1 :]
    return []
