from __future__ import annotations

import numpy as np

from qq_autoreply.config import AppSettings
from qq_autoreply.domain import EventKind, OcrLine, QQWindowInfo, WindowRect
from qq_autoreply.vision.capture import FakeCapture
from qq_autoreply.vision.detector import MessageDetector
from qq_autoreply.vision.windows import FakeWindowProvider, is_qq_candidate_window


class FakeOcr:
    def __init__(self, responses: list[list[OcrLine]]) -> None:
        self.responses = responses

    def recognize(self, image: np.ndarray) -> list[OcrLine]:
        if not self.responses:
            return []
        return self.responses.pop(0)


def frame(color: int | tuple[int, int, int] = 0) -> np.ndarray:
    return np.full((800, 873, 3), color, dtype=np.uint8)


def line(
    text: str,
    left: int,
    right: int,
    confidence: float = 0.99,
    top: int = 100,
) -> OcrLine:
    return OcrLine(
        text=text,
        confidence=confidence,
        left=left,
        top=top,
        right=right,
        bottom=top + 40,
    )


def build_detector(
    frames: list[np.ndarray],
    responses: list[list[OcrLine]],
    target: str = "张三",
) -> MessageDetector:
    settings = AppSettings(target_user_name=target, ocr_min_confidence=0.5)
    window = QQWindowInfo(
        handle=1,
        title="QQ",
        rect=WindowRect(0, 0, 1200, 800),
    )
    detector = MessageDetector(
        settings=settings,
        capture=FakeCapture(frames),
        ocr=FakeOcr(responses),
        window_provider=FakeWindowProvider([window]),
    )
    detector.bind(window)
    return detector


def test_target_mismatch_is_detected() -> None:
    detector = build_detector(
        frames=[frame(1), frame(1)],
        responses=[[line("李四", 100, 250)], [line("李四", 100, 250)]],
        target="张三",
    )

    first = detector.observe()
    result = detector.observe()

    assert first.kind == EventKind.NONE
    assert result.kind == EventKind.TARGET_MISMATCH


def test_group_header_is_rejected_even_when_target_name_is_present() -> None:
    detector = build_detector(
        frames=[frame(1)],
        responses=[[line("群聊 张三", 100, 320)]],
        target="张三",
    )

    result = detector.observe()

    assert result.kind == EventKind.TARGET_MISMATCH


def test_peer_text_event_is_detected() -> None:
    detector = build_detector(
        frames=[frame(1), frame(0), frame(255)],
        responses=[[line("张三", 100, 250)], [line("你好", 20, 220)]],
    )

    first = detector.observe()
    second = detector.observe()

    assert first.kind == EventKind.NONE
    assert second.kind == EventKind.PEER_TEXT
    assert second.event is not None
    assert second.event.text == "你好"


def test_non_text_event_is_detected() -> None:
    detector = build_detector(
        frames=[frame(1), frame(0), frame(255)],
        responses=[[line("张三", 100, 250)], []],
    )

    detector.observe()
    result = detector.observe()

    assert result.kind == EventKind.NON_TEXT
    assert result.event is not None
    assert result.event.text == "[non-text message event]"


def test_colorful_image_or_sticker_is_non_text() -> None:
    detector = build_detector(
        frames=[frame(1), frame(0), frame((0, 0, 255))],
        responses=[[line("张三", 100, 250)], [line("误识别文字", 20, 220)]],
    )

    detector.observe()
    result = detector.observe()

    assert result.kind == EventKind.NON_TEXT


def test_symbol_only_ocr_is_non_text() -> None:
    detector = build_detector(
        frames=[frame(1), frame(0), frame(255)],
        responses=[[line("张三", 100, 250)], [line("!!!...", 20, 220)]],
    )

    detector.observe()
    result = detector.observe()

    assert result.kind == EventKind.NON_TEXT


def test_self_message_is_not_replied_to() -> None:
    detector = build_detector(
        frames=[frame(1), frame(0), frame(255)],
        responses=[[line("张三", 100, 250)], [line("我发出的", 650, 850)]],
    )

    detector.observe()
    result = detector.observe()

    assert result.kind == EventKind.NONE


def test_visible_history_is_loaded_in_order() -> None:
    detector = build_detector(
        frames=[frame(10)],
        responses=[
            [
                line("第一句", 20, 200, top=100),
                line("第二句", 620, 840, top=300),
            ]
        ],
    )

    messages = detector.read_visible_history()

    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.text for message in messages] == ["第一句", "第二句"]


def test_qq_window_filter_rejects_this_application() -> None:
    assert (
        is_qq_candidate_window(
            title="QQ 单会话陪聊助手",
            class_name="Qt6112QWindowIcon",
            process_name="pythonw.exe",
            process_id=10,
            current_process_id=10,
        )
        is False
    )
    assert (
        is_qq_candidate_window(
            title="QQ",
            class_name="TXGuiFoundation",
            process_name="QQ.exe",
            process_id=20,
            current_process_id=10,
        )
        is True
    )
