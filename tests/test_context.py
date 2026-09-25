from __future__ import annotations

from qq_autoreply.context import build_generation_context
from qq_autoreply.domain import ChatMessage


def test_long_context_is_summarized_before_recent_messages() -> None:
    messages = [
        ChatMessage(
            role="user" if index % 2 == 0 else "assistant",
            text=f"消息{index}",
            source="test",
            timestamp=float(index),
        )
        for index in range(10)
    ]

    context = build_generation_context(messages, recent_limit=4)

    assert context[0].role == "system"
    assert context[0].text.startswith("更早对话摘要：")
    assert [message.text for message in context[1:]] == [
        "消息6",
        "消息7",
        "消息8",
        "消息9",
    ]


def test_context_char_budget_keeps_most_recent_messages() -> None:
    messages = [
        ChatMessage(
            role="user",
            text="x" * 100,
            source="uia",
            timestamp=float(index),
        )
        for index in range(10)
    ]

    context = build_generation_context(
        messages,
        recent_limit=10,
        summary_char_limit=200,
        total_char_limit=400,
    )

    assert context[0].role == "system"
    assert len(context) < len(messages)
    assert sum(len(message.text) for message in context) <= 400
    assert context[-1].text == "x" * 100
