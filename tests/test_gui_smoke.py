from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from qq_autoreply.config import MemorySecretStore, SettingsStore
from qq_autoreply.ui.main_window import MainWindow


def test_main_window_contains_target_name_input(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    store = SettingsStore(
        tmp_path / "config.json",
        secret_store=MemorySecretStore(),
    )
    window = MainWindow(settings_store=store)

    assert window.target_name_input is not None
    assert window.bind_button.text() == "绑定当前对话"
    assert window.diagnose_button.text() == "检查环境"
    assert window.auto_start_checkbox.text() == "启动后自动开始"
    assert window.bind_button.isEnabled() is False

    window.target_name_input.setText("张三")
    assert window.bind_button.isEnabled() is True

    window.close()
    app.processEvents()
