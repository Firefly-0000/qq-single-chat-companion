from __future__ import annotations

import time

from ..config import AppSettings
from ..context import build_generation_context
from ..domain import (
    BotState,
    ChatMessage,
    DetectionResult,
    EventKind,
    EventStatus,
    MessageEvent,
    QQWindowInfo,
    TickResult,
)
from ..ports import DetectorPort, ReplyGeneratorPort, ReplySenderPort
from ..storage import Storage


class Orchestrator:
    def __init__(
        self,
        *,
        settings: AppSettings,
        storage: Storage,
        detector: DetectorPort,
        generator: ReplyGeneratorPort,
        sender: ReplySenderPort,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.detector = detector
        self.generator = generator
        self.sender = sender
        self.state = BotState.UNBOUND
        self._pending_events: list[MessageEvent] = []
        self._batch_deadline: float | None = None

    def bind(self, window: QQWindowInfo) -> None:
        self.detector.bind(window)
        self.state = BotState.READY

    def start(self) -> None:
        if self.state == BotState.UNBOUND:
            raise RuntimeError("Bind a QQ conversation before starting")
        self.state = BotState.MONITORING

    def pause(self) -> None:
        self.state = BotState.PAUSED

    def stop(self) -> None:
        self.state = BotState.STOPPED

    def emergency_stop(self) -> None:
        self.settings.auto_send = False
        self.state = BotState.STOPPED

    def tick(self) -> TickResult:
        if self.state != BotState.MONITORING:
            return TickResult(state=self.state, kind=EventKind.NONE)

        if (
            self._pending_events
            and self._batch_deadline is not None
            and time.monotonic() >= self._batch_deadline
        ):
            return self._process_pending_batch()

        detection = self.detector.observe()
        return self._handle_detection(detection)

    def _handle_detection(self, detection: DetectionResult) -> TickResult:
        if detection.kind in {EventKind.NONE}:
            return TickResult(state=self.state, kind=detection.kind, message=detection.reason)

        if detection.kind in {EventKind.ERROR, EventKind.TARGET_MISMATCH, EventKind.LOW_CONFIDENCE}:
            self.state = BotState.PAUSED
            return TickResult(
                state=self.state,
                kind=EventKind.PEER_TEXT,
                message=detection.reason,
                context=self.storage.recent_messages(self.settings.context_recent_messages),
            )

        event = detection.event
        if event is None:
            self.state = BotState.PAUSED
            return TickResult(
                state=self.state,
                kind=EventKind.ERROR,
                message="Detection event is missing",
            )

        if detection.kind == EventKind.NON_TEXT:
            recorded = self.storage.record_event(event, EventStatus.BLOCKED)
            if not recorded:
                return TickResult(state=self.state, kind=EventKind.NONE, message="duplicate event")
            self.storage.add_message(
                ChatMessage(
                    role="user",
                    text=event.text,
                    source="non_text",
                    confidence=event.confidence,
                    timestamp=event.captured_at,
                )
            )
            return TickResult(
                state=self.state,
                kind=EventKind.PEER_TEXT,
                event=event,
                message="non-text message detected; auto reply suppressed",
                context=self.storage.recent_messages(self.settings.context_recent_messages),
            )

        if detection.kind != EventKind.PEER_TEXT:
            return TickResult(state=self.state, kind=detection.kind, message=detection.reason)

        if self.storage.event_exists(event.fingerprint):
            return TickResult(state=self.state, kind=EventKind.NONE, message="duplicate event")

        self.storage.record_event(event, EventStatus.DETECTED)
        self.storage.add_message(
            ChatMessage(
                role="user",
                text=event.text,
                source="ocr",
                confidence=event.confidence,
                timestamp=event.captured_at,
            )
        )
        self._pending_events.append(event)
        if self.settings.batch_window_ms <= 0:
            return self._process_pending_batch()
        self._batch_deadline = time.monotonic() + (self.settings.batch_window_ms / 1000)
        return TickResult(
            state=self.state,
            kind=EventKind.PEER_TEXT,
            event=event,
            message="message queued for batching",
            context=self.storage.recent_messages(self.settings.context_recent_messages),
        )

    def _process_pending_batch(self) -> TickResult:
        events = self._pending_events
        self._pending_events = []
        self._batch_deadline = None
        if not events:
            return TickResult(state=self.state, kind=EventKind.NONE)
        event = events[-1]

        self.state = BotState.GENERATING
        context = self.storage.recent_messages(self.settings.context_recent_messages)
        try:
            reply = self.generator.generate(
                build_generation_context(
                    context,
                    self.settings.context_recent_messages,
                )
            )
        except Exception as exc:
            self.state = BotState.PAUSED
            for pending in events:
                self.storage.update_event_status(pending.event_id, EventStatus.FAILED)
            return TickResult(
                state=self.state,
                kind=EventKind.ERROR,
                event=event,
                message=str(exc),
                context=context,
            )

        blocked = self._blocked_reply(reply)
        if blocked:
            self.state = BotState.PAUSED
            for pending in events:
                self.storage.update_event_status(pending.event_id, EventStatus.BLOCKED)
            return TickResult(
                state=self.state,
                kind=EventKind.ERROR,
                event=event,
                reply=reply,
                message=blocked,
                context=context,
            )

        self.storage.add_message(
            ChatMessage(
                role="assistant",
                text=reply,
                source="deepseek",
                timestamp=event.captured_at,
            )
        )

        if not self.settings.auto_send:
            self.state = BotState.MONITORING
            for pending in events:
                self.storage.update_event_status(pending.event_id, EventStatus.DRAFTED)
            return TickResult(
                state=self.state,
                kind=EventKind.PEER_TEXT,
                event=event,
                reply=reply,
                message="reply drafted; auto send is disabled",
                context=self.storage.recent_messages(self.settings.context_recent_messages),
            )

        self.state = BotState.SENDING
        try:
            self.sender.send(reply)
        except Exception as exc:
            self.state = BotState.PAUSED
            for pending in events:
                self.storage.update_event_status(
                    pending.event_id,
                    EventStatus.SEND_UNCERTAIN,
                )
            return TickResult(
                state=self.state,
                kind=EventKind.ERROR,
                event=event,
                reply=reply,
                message=f"send failed or uncertain: {exc}",
                context=self.storage.recent_messages(self.settings.context_recent_messages),
            )

        for pending in events:
            self.storage.update_event_status(pending.event_id, EventStatus.SENT)
        self.state = BotState.MONITORING
        return TickResult(
            state=self.state,
            kind=EventKind.PEER_TEXT,
            event=event,
            reply=reply,
            message="reply sent",
            context=self.storage.recent_messages(self.settings.context_recent_messages),
        )

    def _blocked_reply(self, reply: str) -> str | None:
        if not reply.strip():
            return "empty reply blocked"
        if len(reply) > self.settings.max_reply_chars:
            return "reply exceeds maximum length"
        for topic in self.settings.persona.forbidden_topics:
            if topic and topic in reply:
                return f"reply contains forbidden topic: {topic}"
        return None
