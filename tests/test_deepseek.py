from __future__ import annotations

from types import SimpleNamespace

import pytest

from qq_autoreply.config import AppSettings
from qq_autoreply.deepseek import DeepSeekReplyGenerator, GenerationError
from qq_autoreply.domain import ChatMessage


class FakeCompletions:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or ["这是一条测试回复"]
        self.calls = 0
        self.last_kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> object:
        self.last_kwargs = kwargs
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.responses[index])
                )
            ]
        )


class FakeClient:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


def test_missing_api_key_raises() -> None:
    generator = DeepSeekReplyGenerator(AppSettings(api_key=""))

    with pytest.raises(GenerationError):
        generator.generate([])


def test_generate_returns_text() -> None:
    generator = DeepSeekReplyGenerator(AppSettings(api_key="sk-test"))
    client = FakeClient()
    generator._client = client  # type: ignore[assignment]

    reply = generator.generate(
        [ChatMessage(role="user", text="你好", source="ocr", timestamp=1.0)]
    )

    assert reply == "这是一条测试回复"
    assert client.chat.completions.last_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


def test_empty_response_is_retried() -> None:
    generator = DeepSeekReplyGenerator(AppSettings(api_key="sk-test"))
    client = FakeClient(["", "重试成功"])
    generator._client = client  # type: ignore[assignment]

    reply = generator.generate(
        [ChatMessage(role="user", text="你好", source="ocr", timestamp=1.0)]
    )

    assert reply == "重试成功"
    assert client.chat.completions.calls == 2
