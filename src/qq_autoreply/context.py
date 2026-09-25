from __future__ import annotations

from .domain import ChatMessage


def build_generation_context(
    messages: list[ChatMessage],
    recent_limit: int,
    summary_char_limit: int = 6_000,
    total_char_limit: int = 30_000,
) -> list[ChatMessage]:
    if not messages:
        return []

    recent = list(messages[-recent_limit:])
    while len(recent) > 1 and _character_count(recent) > total_char_limit:
        recent.pop(0)

    older_count = max(0, len(messages) - len(recent))
    older = messages[:older_count]
    if not older:
        return recent

    summary_lines: list[str] = []
    for message in older:
        speaker = "对方" if message.role == "user" else "回复"
        summary_lines.append(f"{speaker}: {message.text}")
    summary = "更早对话摘要：" + "；".join(summary_lines)
    summary = summary[-summary_char_limit:]
    while len(recent) > 1 and len(summary) + _character_count(recent) > total_char_limit:
        recent.pop(0)
    summary_budget = max(0, total_char_limit - _character_count(recent))
    summary = "" if summary_budget == 0 else summary[-summary_budget:]
    if summary:
        return [
            ChatMessage(
                role="system",
                text=summary,
                source="summary",
                timestamp=older[-1].timestamp,
            ),
            *recent,
        ]
    if len(recent) == 1 and len(recent[0].text) > total_char_limit:
        latest = recent[0]
        recent = [
            ChatMessage(
                role=latest.role,
                text=latest.text[-total_char_limit:],
                source=latest.source,
                confidence=latest.confidence,
                timestamp=latest.timestamp,
            )
        ]
    return recent


def _character_count(messages: list[ChatMessage]) -> int:
    return sum(len(message.text) for message in messages)
