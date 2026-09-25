from __future__ import annotations

import hashlib
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

from ..domain import ChatMessage, EventKind, QQWindowInfo
from ..text import normalize_text

MESSAGE_AREA_CLASS = "chat-msg-area need-inverted-colors"
HEADER_CLASS = "chat-header__contact-name"
MESSAGE_CLASS = "message"
CONTAINER_CLASS_PREFIX = "msg-content-container"
SELF_CONTAINER_MARKER = "message-container--self"

GROUP_MARKERS = ("群聊", "群组", "频道", "成员列表")
NON_TEXT_PLACEHOLDER = "[图片/表情]"


class UiaChatError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UiaHeader:
    name: str
    group_markers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UiaChatMessage:
    key: str
    runtime_id: tuple[int, ...]
    role: Literal["user", "assistant"]
    text: str
    kind: EventKind
    confidence: float
    captured_at: float
    top: int

    def to_chat_message(self) -> ChatMessage:
        return ChatMessage(
            role=self.role,
            text=self.text,
            source="uia",
            confidence=self.confidence,
            timestamp=self.captured_at,
        )


def _ensure_com_initialized() -> None:
    try:
        import comtypes
    except Exception:
        return
    with suppress(OSError):
        comtypes.CoInitialize()


def _class_name(node: object) -> str:
    info = getattr(node, "element_info", node)
    return str(getattr(info, "class_name", "") or "")


def _name(node: object) -> str:
    try:
        value = node.window_text()
    except Exception:
        value = getattr(getattr(node, "element_info", node), "name", "")
    return str(value or "")


def _runtime_id(node: object) -> tuple[int, ...]:
    info = getattr(node, "element_info", node)
    value = getattr(info, "runtime_id", ()) or ()
    try:
        return tuple(int(item) for item in value)
    except (TypeError, ValueError):
        return ()


def _top(node: object) -> int:
    info = getattr(node, "element_info", node)
    try:
        return int(info.rectangle.top)
    except Exception:
        return 0


def _descendants(node: object, **kwargs: object) -> list[object]:
    try:
        return list(node.descendants(**kwargs))
    except Exception as exc:
        raise UiaChatError(f"UIA descendant query failed: {exc.__class__.__name__}") from exc


def _children(node: object, **kwargs: object) -> list[object]:
    try:
        return list(node.children(**kwargs))
    except Exception as exc:
        raise UiaChatError(f"UIA child query failed: {exc.__class__.__name__}") from exc


class UiaChatReader:
    def __init__(self) -> None:
        self.window: QQWindowInfo | None = None
        self._root: object | None = None
        self._lock = threading.RLock()

    def bind(self, window: QQWindowInfo) -> None:
        with self._lock:
            _ensure_com_initialized()
            try:
                from pywinauto.uia_element_info import UIAElementInfo

                self._root = UIAElementInfo(window.handle)
            except Exception as exc:
                raise UiaChatError(f"Unable to initialize UIA for QQ: {exc}") from exc
            self.window = window

    def read_header(self) -> UiaHeader:
        with self._lock:
            root = self._require_root()
            headers = _descendants(root, class_name=HEADER_CLASS)
            if not headers:
                raise UiaChatError("QQ conversation header was not found")
            header = headers[0]
            markers: list[str] = []
            parent = getattr(getattr(header, "element_info", header), "parent", None)
            if parent is not None:
                for child in _children(parent):
                    child_name = _name(child)
                    if any(marker in child_name for marker in GROUP_MARKERS):
                        markers.append(child_name)
            return UiaHeader(name=_name(header).strip(), group_markers=tuple(markers))

    def read_messages(self) -> list[UiaChatMessage]:
        with self._lock:
            root = self._require_root()
            areas = _descendants(root, class_name=MESSAGE_AREA_CLASS)
            if not areas:
                raise UiaChatError("QQ chat message area was not found")
            nodes = _descendants(areas[0], class_name=MESSAGE_CLASS)
            messages = [message for node in nodes if (message := self._parse_message(node))]
            messages.sort(key=lambda message: message.top)
            return messages

    def wait_for_self_message(
        self,
        text: str,
        *,
        timeout_seconds: float = 5.0,
        poll_seconds: float = 0.1,
    ) -> bool:
        expected = normalize_text(text)
        baseline = {
            message.key for message in self.read_messages() if message.role == "assistant"
        }
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for message in self.read_messages():
                if message.role != "assistant" or message.key in baseline:
                    continue
                observed = normalize_text(message.text)
                if expected and (expected in observed or observed in expected):
                    return True
            time.sleep(poll_seconds)
        return False

    def _require_root(self) -> object:
        if self._root is None:
            raise UiaChatError("No QQ window is bound")
        return self._root

    def _parse_message(self, node: object) -> UiaChatMessage | None:
        groups = _descendants(node, control_type="Group")
        containers = [
            group
            for group in groups
            if _class_name(group).startswith(CONTAINER_CLASS_PREFIX)
        ]
        if not containers:
            return None
        container = max(containers, key=lambda item: len(_name(item)))
        all_classes = " ".join(_class_name(group) for group in groups)
        role: Literal["user", "assistant"] = (
            "assistant" if SELF_CONTAINER_MARKER in all_classes else "user"
        )
        direct_texts = [
            _name(child).strip()
            for child in _children(container, control_type="Text")
            if _name(child).strip()
        ]
        text = "\n".join(direct_texts).strip()
        container_class = _class_name(container)
        has_image = bool(_descendants(container, control_type="Image"))
        if text:
            kind = EventKind.SELF_TEXT if role == "assistant" else EventKind.PEER_TEXT
            confidence = 1.0
        else:
            kind = EventKind.NON_TEXT
            text = NON_TEXT_PLACEHOLDER
            confidence = 0.0

        runtime_id = _runtime_id(node)
        identity = (
            f"{role}|{runtime_id}|{kind.value}|"
            f"{normalize_text(text)}|{'image' if has_image else container_class}"
        )
        return UiaChatMessage(
            key=hashlib.sha256(identity.encode()).hexdigest(),
            runtime_id=runtime_id,
            role=role,
            text=text,
            kind=kind,
            confidence=confidence,
            captured_at=time.time(),
            top=_top(node),
        )
