from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from qq_autoreply.config import MemorySecretStore, SettingsStore
from qq_autoreply.goutoujunshi import (
    GoutoujunshiCandidate,
    GoutoujunshiResult,
)
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
    assert window.skill_enabled_checkbox.text() == "启用狗头军师模式"
    assert window.tabs.tabText(2) == "军师"
    assert window.bind_button.isEnabled() is False

    window.target_name_input.setText("张三")
    assert window.bind_button.isEnabled() is True

    window._render_skill_result(
        GoutoujunshiResult(
            support="先接住情绪",
            facts=["事实"],
            hypotheses=["推测"],
            unknowns=["未知"],
            strategy="降压",
            recommendation="先回应",
            next_step="等待反馈",
            stop_condition="明确拒绝时停止",
            candidates=[
                GoutoujunshiCandidate("候选一", "理由一", "代价一"),
                GoutoujunshiCandidate("候选二", "理由二", "代价二"),
            ],
            best_index=0,
        )
    )
    assert window.skill_candidates_table.rowCount() == 2
    assert "候选一" in window.skill_candidates_table.item(0, 0).text()

    window.close()
    app.processEvents()
