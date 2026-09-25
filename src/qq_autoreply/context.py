from __future__ import annotations

from .domain import ChatMessage
from .text import normalize_text

_IGNORED_PLACEHOLDERS = {
    "[图片/表情]",
    "[non-text message event]",
    "[非文字消息]",
}


def build_generation_context(
    messages: list[ChatMessage],
    recent_limit: int,
    summary_char_limit: int = 6_000,
    total_char_limit: int = 30_000,
) -> list[ChatMessage]:
    history = _prepare_history(messages)
    if not history:
        return []

    recent = list(history[-recent_limit:])
    while len(recent) > 1 and _character_count(recent) > total_char_limit:
        recent.pop(0)

    older_count = max(0, len(history) - len(recent))
    older = history[:older_count]
    if not older:
        return recent

    summary_lines: list[str] = []
    for message in older:
        speaker = "对方" if message.role == "user" else "我"
        summary_lines.append(f"{speaker}: {message.text}")
    summary = "更早对话摘要：\n" + "\n".join(summary_lines)
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


def _prepare_history(messages: list[ChatMessage]) -> list[ChatMessage]:
    prepared: list[ChatMessage] = []
    previous_key: tuple[str, str] | None = None
    for message in messages:
        text = message.text.strip()
        if not text or text in _IGNORED_PLACEHOLDERS or message.source == "non_text":
            continue
        key = (message.role, normalize_text(text))
        if key == previous_key:
            continue
        prepared.append(message)
        previous_key = key
    return prepared
