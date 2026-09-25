from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import AppSettings
from ..domain import (
    ChatMessage,
    DetectionResult,
    EventKind,
    MessageEvent,
    OcrLine,
    QQWindowInfo,
    WindowRect,
)
from ..text import has_meaningful_text, normalize_text
from .capture import MssCapture
from .layout import LayoutProfile, QQChatLayout, build_layout
from .ocr import RapidOcrEngine
from .windows import Win32WindowProvider


@dataclass(slots=True)
class _LineGroup:
    lines: list[OcrLine]

    @property
    def text(self) -> str:
        return " ".join(line.text.strip() for line in self.lines if line.text.strip()).strip()

    @property
    def confidence(self) -> float:
        if not self.lines:
            return 0.0
        return sum(line.confidence for line in self.lines) / len(self.lines)

    @property
    def left(self) -> int:
        return min(line.left for line in self.lines)

    @property
    def top(self) -> int:
        return min(line.top for line in self.lines)

    @property
    def right(self) -> int:
        return max(line.right for line in self.lines)

    @property
    def bottom(self) -> int:
        return max(line.bottom for line in self.lines)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


class MessageDetector:
    def __init__(
        self,
        *,
        settings: AppSettings,
        capture: MssCapture,
        ocr: RapidOcrEngine,
        window_provider: Win32WindowProvider,
    ) -> None:
        self.settings = settings
        self.capture = capture
        self.ocr = ocr
        self.window_provider = window_provider
        self.window: QQWindowInfo | None = None
        self.layout: QQChatLayout | None = None
        self._last_frame: np.ndarray | None = None
        self._last_fingerprint: str | None = None
        self._header_checks = 0
        self._target_mismatch_count = 0

    def bind(self, window: QQWindowInfo) -> None:
        self.window = window
        self.layout = build_layout(window, LayoutProfile())
        self._last_frame = None
        self._last_fingerprint = None
        self._header_checks = 0
        self._target_mismatch_count = 0

    def validate_target(self) -> DetectionResult | None:
        return self._validate_target()

    def read_visible_history(self, limit: int = 50) -> list[ChatMessage]:
        if self.layout is None:
            return []
        frame = self.capture.capture(self.layout.messages)
        groups = self._group_lines(self.ocr.recognize(frame))
        peer_ratio = self.layout.messages.width * 0.62
        messages: list[ChatMessage] = []
        now = time.time()
        for index, group in enumerate(sorted(groups, key=lambda item: item.top)):
            text = group.text.strip()
            if not text:
                continue
            messages.append(
                ChatMessage(
                    role="user" if group.center_x < peer_ratio else "assistant",
                    text=text,
                    source="ocr_history",
                    confidence=group.confidence,
                    timestamp=now + index,
                )
            )
        return messages[-limit:]

    def observe(self) -> DetectionResult:
        if self.window is None or self.layout is None:
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
            self.layout = build_layout(self.window, LayoutProfile())

        if self._header_checks % 2 == 0 or self._target_mismatch_count > 0:
            validation = self._validate_target()
            if validation is not None:
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

        message_frame = self.capture.capture(self.layout.messages)
        if self._last_frame is None:
            self._last_frame = message_frame
            return DetectionResult(kind=EventKind.NONE, reason="baseline captured")

        change_score = self._change_score(self._last_frame, message_frame)
        if change_score < self.settings.frame_change_threshold:
            return DetectionResult(kind=EventKind.NONE, reason="no significant frame change")

        changed_bounds = self._changed_bounds(self._last_frame, message_frame)
        if changed_bounds is not None and self._colorful_ratio(
            message_frame,
            changed_bounds,
        ) >= self.settings.colorful_region_threshold:
            fingerprint = self._pixel_fingerprint(message_frame)
            self._last_frame = message_frame
            if fingerprint == self._last_fingerprint:
                return DetectionResult(kind=EventKind.NONE, reason="known image event")
            self._last_fingerprint = fingerprint
            return DetectionResult(
                kind=EventKind.NON_TEXT,
                event=self._event(
                    kind=EventKind.NON_TEXT,
                    text="[non-text message event]",
                    confidence=0.0,
                    fingerprint=fingerprint,
                ),
            )

        lines = self.ocr.recognize(message_frame)
        if changed_bounds is not None:
            margin = 24
            lines = [
                line
                for line in lines
                if line.center_y >= changed_bounds.top - margin
                and line.center_y <= changed_bounds.bottom + margin
            ]
        groups = self._group_lines(lines)
        groups = [group for group in groups if has_meaningful_text(group.text)]
        if not groups:
            fingerprint = self._pixel_fingerprint(message_frame)
            self._last_frame = message_frame
            if fingerprint == self._last_fingerprint:
                return DetectionResult(kind=EventKind.NONE, reason="known non-text event")
            self._last_fingerprint = fingerprint
            return DetectionResult(
                kind=EventKind.NON_TEXT,
                event=self._event(
                    kind=EventKind.NON_TEXT,
                    text="[non-text message event]",
                    confidence=0.0,
                    fingerprint=fingerprint,
                ),
            )

        peer_ratio = self.layout.messages.width * 0.62
        peer_groups = [group for group in groups if group.center_x < peer_ratio]
        self_groups = [group for group in groups if group.center_x >= peer_ratio]
        last_peer = max(peer_groups, key=lambda group: group.bottom, default=None)
        last_self = max(self_groups, key=lambda group: group.bottom, default=None)

        if last_self is not None and (
            last_peer is None or last_self.bottom > last_peer.bottom
        ):
            self._last_frame = message_frame
            return DetectionResult(kind=EventKind.NONE, reason="last message belongs to self")

        if last_peer is None:
            fingerprint = self._pixel_fingerprint(message_frame)
            self._last_frame = message_frame
            if fingerprint == self._last_fingerprint:
                return DetectionResult(kind=EventKind.NONE, reason="known non-text event")
            self._last_fingerprint = fingerprint
            return DetectionResult(
                kind=EventKind.NON_TEXT,
                event=self._event(
                    kind=EventKind.NON_TEXT,
                    text="[non-text message event]",
                    confidence=0.0,
                    fingerprint=fingerprint,
                ),
            )

        if last_peer.confidence < self.settings.ocr_min_confidence:
            self._last_frame = message_frame
            return DetectionResult(
                kind=EventKind.LOW_CONFIDENCE,
                reason=f"OCR confidence {last_peer.confidence:.2f} is below threshold",
            )

        crop = message_frame[
            max(0, last_peer.top) : max(1, last_peer.bottom),
            max(0, last_peer.left) : max(1, last_peer.right),
        ]
        fingerprint = hashlib.sha256(
            (
                f"{normalize_text(last_peer.text)}|"
                f"{self._pixel_fingerprint(crop)}|"
                f"{self._pixel_fingerprint(message_frame)}"
            ).encode()
        ).hexdigest()
        self._last_frame = message_frame
        if fingerprint == self._last_fingerprint:
            return DetectionResult(kind=EventKind.NONE, reason="duplicate message")
        self._last_fingerprint = fingerprint
        return DetectionResult(
            kind=EventKind.PEER_TEXT,
            event=self._event(
                kind=EventKind.PEER_TEXT,
                text=last_peer.text,
                confidence=last_peer.confidence,
                fingerprint=fingerprint,
            ),
        )

    def _validate_target(self) -> DetectionResult | None:
        if self.layout is None:
            return DetectionResult(kind=EventKind.ERROR, reason="No layout available")
        header_frame = self.capture.capture(self.layout.header)
        lines = self.ocr.recognize(header_frame)
        observed = normalize_text(" ".join(line.text for line in lines))
        expected = normalize_text(self.settings.target_user_name)
        group_markers = ("群聊", "群组", "频道", "成员", "人)")
        if any(normalize_text(marker) in observed for marker in group_markers):
            return DetectionResult(
                kind=EventKind.TARGET_MISMATCH,
                reason="Group-chat marker detected in the active conversation header",
            )
        if expected and expected not in observed:
            return DetectionResult(
                kind=EventKind.TARGET_MISMATCH,
                reason=f"Expected target {self.settings.target_user_name!r}, observed {observed!r}",
            )
        return None

    @staticmethod
    def _change_score(previous: np.ndarray, current: np.ndarray) -> float:
        if previous.shape != current.shape:
            return 1.0
        difference = cv2.absdiff(previous, current)
        return float(np.mean(difference) / 255.0)

    @staticmethod
    def _changed_bounds(previous: np.ndarray, current: np.ndarray) -> WindowRect | None:
        if previous.shape != current.shape:
            return None
        difference = cv2.absdiff(previous, current)
        gray = cv2.cvtColor(difference, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 8, 255, cv2.THRESH_BINARY)
        coordinates = cv2.findNonZero(mask)
        if coordinates is None:
            return None
        left, top, width, height = cv2.boundingRect(coordinates)
        return WindowRect(left=left, top=top, right=left + width, bottom=top + height)

    @staticmethod
    def _colorful_ratio(image: np.ndarray, bounds: WindowRect) -> float:
        crop = image[
            max(0, bounds.top) : max(1, bounds.bottom),
            max(0, bounds.left) : max(1, bounds.right),
        ]
        if crop.size == 0:
            return 0.0
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        colorful = (saturation >= 80) & (value >= 80)
        return float(np.count_nonzero(colorful) / colorful.size)

    @staticmethod
    def _group_lines(lines: list[OcrLine]) -> list[_LineGroup]:
        if not lines:
            return []
        ordered = sorted(lines, key=lambda line: (line.top, line.left))
        groups: list[_LineGroup] = []
        for line in ordered:
            if not groups:
                groups.append(_LineGroup([line]))
                continue
            current = groups[-1]
            vertical_gap = line.top - current.bottom
            allowed_gap = max(8, int((current.bottom - current.top) * 0.45))
            horizontal_overlap = min(line.right, current.right) - max(line.left, current.left)
            if vertical_gap <= allowed_gap and horizontal_overlap > 0:
                current.lines.append(line)
            else:
                groups.append(_LineGroup([line]))
        return groups

    @staticmethod
    def _pixel_fingerprint(image: np.ndarray) -> str:
        if image.size == 0:
            return "empty"
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        reduced = cv2.resize(gray, (24, 24), interpolation=cv2.INTER_AREA)
        return hashlib.sha256(reduced.tobytes()).hexdigest()

    @staticmethod
    def _event(*, kind: EventKind, text: str, confidence: float, fingerprint: str) -> MessageEvent:
        return MessageEvent(
            event_id=str(uuid.uuid4()),
            kind=kind,
            fingerprint=fingerprint,
            text=text,
            confidence=confidence,
            captured_at=time.time(),
        )
