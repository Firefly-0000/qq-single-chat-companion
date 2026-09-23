from __future__ import annotations

from pathlib import Path

from qq_autoreply.config import AppSettings, MemorySecretStore, SettingsStore


def test_settings_round_trip_keeps_api_key_out_of_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    secrets = MemorySecretStore()
    store = SettingsStore(config_path, secret_store=secrets)
    settings = AppSettings(
        target_user_name="张三",
        api_key="sk-test-secret",
        model="deepseek-v4-pro",
    )

    store.save(settings)
    loaded = store.load()

    assert "sk-test-secret" not in config_path.read_text(encoding="utf-8")
    assert loaded.api_key == "sk-test-secret"
    assert loaded.target_user_name == "张三"
    assert loaded.model == "deepseek-v4-pro"


def test_environment_key_is_used_when_secret_store_is_empty(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    store = SettingsStore(
        tmp_path / "config.json",
        secret_store=MemorySecretStore(),
    )

    assert store.load().api_key == "sk-env"


def test_corrupt_config_falls_back_to_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{broken", encoding="utf-8")
    store = SettingsStore(config_path, secret_store=MemorySecretStore())

    settings = store.load()

    assert settings.model == "deepseek-flash"
