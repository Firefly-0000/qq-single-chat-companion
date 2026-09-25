from __future__ import annotations

import json
from types import SimpleNamespace

from qq_autoreply.config import AppSettings
from qq_autoreply.domain import ChatMessage
from qq_autoreply.goutoujunshi import (
    GoutoujunshiGenerator,
    SwitchableReplyGenerator,
)


class FakeCompletions:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def create(self, **_: object) -> object:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(self.payload, ensure_ascii=False)
                    )
                )
            ]
        )


class FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(payload))


def result_payload() -> dict[str, object]:
    return {
        "support": "能理解你现在有点难受。",
        "facts": ["对方说最近忙"],
        "hypotheses": ["可能确实需要时间"],
        "unknowns": ["对方真实安排"],
        "strategy": "降压",
        "recommendation": "先接住安排",
        "next_step": "等对方有空再确认",
        "stop_condition": "明确拒绝时停止",
        "candidates": [
            {"text": "好，你先忙。", "reason": "减少压力", "tradeoff": "暂不约时间"},
            {"text": "那你有空再说。", "reason": "保留空间", "tradeoff": "显得略冷淡"},
        ],
        "best_index": 0,
    }


def messages() -> list[ChatMessage]:
    return [
        ChatMessage(
            role="user",
            text="最近有点忙，晚点聊",
            source="ocr",
            timestamp=1.0,
            confidence=0.99,
        )
    ]


def test_skill_prompt_embeds_bundled_instructions() -> None:
    generator = GoutoujunshiGenerator(AppSettings())

    prompt = generator.build_system_prompt("最近有点忙")

    assert "狗头军师" in prompt
    assert "实战话术编排器" in prompt
    assert "只输出一个 JSON 对象" in prompt


def test_skill_returns_best_candidate() -> None:
    generator = GoutoujunshiGenerator(AppSettings(api_key="sk-test"))
    generator._client = FakeClient(result_payload())  # type: ignore[assignment]

    reply = generator.generate(messages())

    assert reply == "好，你先忙。"
    assert generator.last_result is not None
    assert generator.last_result.best_reply == "好，你先忙。"


def test_switchable_generator_uses_skill_mode() -> None:
    class Standard:
        def configure(self, settings: AppSettings) -> None:
            pass

        def generate(self, messages: list[ChatMessage]) -> str:
            return "普通回复"

    settings = AppSettings(api_key="sk-test", reply_mode="goutoujunshi")
    skill = GoutoujunshiGenerator(settings)
    skill._client = FakeClient(result_payload())  # type: ignore[assignment]
    generator = SwitchableReplyGenerator(
        settings=settings,
        standard=Standard(),
        skill=skill,
    )

    assert generator.generate(messages()) == "好，你先忙。"
    assert generator.last_skill_result is not None
