from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class PersonaSettings(BaseModel):
    display_name: str = ""
    relationship: str = "熟悉的朋友"
    tone: str = "自然、温和、简短"
    reply_length: str = "通常 1 到 3 句"
    forbidden_topics: list[str] = Field(
        default_factory=lambda: ["转账", "验证码", "密码", "银行卡", "身份证", "付款链接"]
    )


class AppSettings(BaseModel):
    target_user_name: str = ""
    api_key: str = ""
    api_base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    poll_interval_ms: int = Field(default=250, ge=100, le=10_000)
    request_timeout_seconds: int = Field(default=60, ge=5, le=300)
    max_reply_chars: int = Field(default=500, ge=10, le=5_000)
    max_reply_tokens: int = Field(default=300, ge=32, le=4_096)
    context_recent_messages: int = Field(default=200, ge=20, le=1_000)
    context_summary_chars: int = Field(default=6_000, ge=500, le=30_000)
    context_char_limit: int = Field(default=30_000, ge=4_000, le=100_000)
    reply_mode: Literal["standard", "goutoujunshi"] = "standard"
    skill_relationship: str = "熟悉的朋友"
    skill_style: str = "自然、简短、有分寸"
    skill_goal: str = "自然陪聊"
    batch_window_ms: int = Field(default=3_000, ge=0, le=30_000)
    frame_change_threshold: float = Field(default=0.003, ge=0.0001, le=0.25)
    ocr_min_confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    colorful_region_threshold: float = Field(default=0.12, ge=0.0, le=1.0)
    focus_guard_idle_seconds: float = Field(default=1.2, ge=0.0, le=10.0)
    auto_start: bool = False
    auto_send: bool = False
    persona: PersonaSettings = Field(default_factory=PersonaSettings)


class SecretStore(Protocol):
    def get(self) -> str | None: ...

    def set(self, value: str) -> None: ...


class KeyringSecretStore:
    SERVICE = "qq-autoreply"
    USERNAME = "deepseek-api-key"

    def get(self) -> str | None:
        try:
            import keyring

            return keyring.get_password(self.SERVICE, self.USERNAME)
        except Exception:
            return None

    def set(self, value: str) -> None:
        import keyring

        if value:
            keyring.set_password(self.SERVICE, self.USERNAME, value)


class MemorySecretStore:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str | None:
        return self.value or None

    def set(self, value: str) -> None:
        self.value = value


class SettingsStore:
    def __init__(
        self,
        path: Path | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.path = path or project_root() / "data" / "config.json"
        self.secret_store = secret_store or KeyringSecretStore()

    def load(self) -> AppSettings:
        payload: dict[str, object] = {}
        if self.path.exists():
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                payload = {}
        settings = AppSettings.model_validate(payload)
        api_key = self.secret_store.get() or os.getenv("DEEPSEEK_API_KEY", "")
        return settings.model_copy(update={"api_key": api_key})

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = settings.model_dump(exclude={"api_key"})
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)
        if settings.api_key:
            self.secret_store.set(settings.api_key)
