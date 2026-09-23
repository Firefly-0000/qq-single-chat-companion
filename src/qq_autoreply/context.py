from __future__ import annotations

from .domain import ChatMessage


def build_generation_context(
    messages: list[ChatMessage],
    recent_limit: int,
    summary_char_limit: int = 800,
) -> list[ChatMessage]:
    if len(messages) <= recent_limit:
        return messages

    older = messages[:-recent_limit]
    recent = messages[-recent_limit:]
    summary_lines: list[str] = []
    for message in older:
        speaker = "对方" if message.role == "user" else "回复"
        summary_lines.append(f"{speaker}: {message.text}")
    summary = "更早对话摘要：" + "；".join(summary_lines)
    if len(summary) > summary_char_limit:
        summary = summary[-summary_char_limit:]
    return [
        ChatMessage(
            role="system",
            text=summary,
            source="summary",
            timestamp=older[-1].timestamp,
        ),
        *recent,
    ]
