from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings, SettingsStore
from ..domain import BotState, ChatMessage, TickResult
from ..service.orchestrator import Orchestrator
from ..service.runtime import Runtime, TargetBindingError
from .worker import EngineWorker, SkillAnalysisWorker, SkillFillWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, settings_store: SettingsStore | None = None) -> None:
        super().__init__()
        self.setWindowTitle("QQ 单会话陪聊助手")
        self.resize(1120, 760)
        self.settings_store = settings_store or SettingsStore()
        self.settings = self.settings_store.load()
        self.runtime = Runtime.create(self.settings)
        self.orchestrator = Orchestrator(
            settings=self.settings,
            storage=self.runtime.storage,
            detector=self.runtime.detector,
            generator=self.runtime.generator,
            sender=self.runtime.sender,
        )
        self.worker: EngineWorker | None = None
        self.skill_analysis_worker: SkillAnalysisWorker | None = None
        self.skill_fill_worker: SkillFillWorker | None = None
        self._rendered_skill_result: object | None = None
        self.bound_window = None
        self._build_ui()
        self._load_settings_into_ui()
        self._append_log("程序已启动。请先打开目标私聊并完成绑定。")
        QTimer.singleShot(0, self._auto_start_if_configured)

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_control_tab(), "控制")
        self.tabs.addTab(self._build_conversation_tab(), "对话")
        self.tabs.addTab(self._build_skill_tab(), "军师")
        self.tabs.addTab(self._build_settings_tab(), "设置")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("未绑定")

    def _build_control_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        bind_row = QHBoxLayout()
        bind_row.addWidget(QLabel("目标用户名称"))
        self.target_name_input = QLineEdit()
        self.target_name_input.setPlaceholderText("输入 QQ 当前显示的昵称或备注名")
        self.target_name_input.textChanged.connect(self._update_bind_button_state)
        bind_row.addWidget(self.target_name_input, stretch=1)
        self.bind_button = QPushButton("绑定当前对话")
        self.bind_button.clicked.connect(self._bind_current_chat)
        bind_row.addWidget(self.bind_button)
        layout.addLayout(bind_row)

        control_row = QHBoxLayout()
        self.start_button = QPushButton("开始")
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")
        self.emergency_button = QPushButton("急停")
        self.start_button.clicked.connect(self._start)
        self.pause_button.clicked.connect(self._pause)
        self.stop_button.clicked.connect(self._stop)
        self.emergency_button.clicked.connect(self._emergency_stop)
        for button in (
            self.start_button,
            self.pause_button,
            self.stop_button,
            self.emergency_button,
        ):
            control_row.addWidget(button)
        control_row.addStretch(1)
        self.auto_send_checkbox = QCheckBox("启用自动发送")
        self.auto_send_checkbox.toggled.connect(self._toggle_auto_send)
        control_row.addWidget(self.auto_send_checkbox)
        self.auto_start_checkbox = QCheckBox("启动后自动开始")
        self.auto_start_checkbox.toggled.connect(self._toggle_auto_start)
        control_row.addWidget(self.auto_start_checkbox)
        layout.addLayout(control_row)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        state_row = QHBoxLayout()
        state_row.addWidget(QLabel("状态"))
        self.state_label = QLabel(BotState.UNBOUND.value)
        self.state_label.setObjectName("stateLabel")
        state_row.addWidget(self.state_label)
        state_row.addStretch(1)
        layout.addLayout(state_row)

        self.event_label = QLabel("暂无事件")
        self.event_label.setWordWrap(True)
        layout.addWidget(self.event_label)

        layout.addWidget(QLabel("运行日志"))
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(1000)
        layout.addWidget(self.log_output, stretch=1)
        return page

    def _build_conversation_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)

        toolbar = QHBoxLayout()
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self._refresh_context)
        clear_button = QPushButton("清空上下文")
        clear_button.clicked.connect(self._clear_context)
        save_context_button = QPushButton("保存上下文")
        save_context_button.clicked.connect(self._save_context)
        toolbar.addWidget(refresh_button)
        toolbar.addWidget(clear_button)
        toolbar.addWidget(save_context_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.context_output = QPlainTextEdit()
        self.context_output.setReadOnly(False)
        layout.addWidget(self.context_output, stretch=1)
        return page

    def _build_skill_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.skill_enabled_checkbox = QCheckBox("启用狗头军师模式")
        self.skill_enabled_checkbox.toggled.connect(self._toggle_skill_mode)
        layout.addWidget(self.skill_enabled_checkbox)

        form = QFormLayout()
        self.skill_relationship_input = QLineEdit()
        self.skill_style_input = QLineEdit()
        self.skill_goal_input = QLineEdit()
        form.addRow("关系", self.skill_relationship_input)
        form.addRow("表达风格", self.skill_style_input)
        form.addRow("当前目标", self.skill_goal_input)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.skill_analyze_button = QPushButton("分析当前上下文")
        self.skill_analyze_button.clicked.connect(self._analyze_with_skill)
        self.skill_fill_button = QPushButton("填入首选草稿")
        self.skill_fill_button.clicked.connect(self._fill_selected_skill_candidate)
        actions.addWidget(self.skill_analyze_button)
        actions.addWidget(self.skill_fill_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.skill_status_label = QLabel("狗头军师尚未运行")
        layout.addWidget(self.skill_status_label)

        self.skill_summary_output = QPlainTextEdit()
        self.skill_summary_output.setReadOnly(True)
        self.skill_summary_output.setMaximumHeight(170)
        layout.addWidget(self.skill_summary_output)

        self.skill_candidates_table = QTableWidget(0, 3)
        self.skill_candidates_table.setHorizontalHeaderLabels(["候选", "理由", "代价"])
        self.skill_candidates_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.skill_candidates_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.skill_candidates_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.skill_candidates_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.skill_candidates_table, stretch=1)
        return page

    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.base_url_input = QLineEdit()
        self.model_input = QLineEdit()
        self.poll_interval_input = QSpinBox()
        self.poll_interval_input.setRange(250, 10_000)
        self.poll_interval_input.setSuffix(" ms")
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(5, 300)
        self.timeout_input.setSuffix(" 秒")
        self.max_reply_input = QSpinBox()
        self.max_reply_input.setRange(10, 5_000)
        self.max_reply_input.setSuffix(" 字")
        self.persona_name_input = QLineEdit()
        self.relationship_input = QLineEdit()
        self.tone_input = QLineEdit()
        self.forbidden_topics_input = QLineEdit()

        form.addRow("DeepSeek API Key", self.api_key_input)
        form.addRow("Base URL", self.base_url_input)
        form.addRow("模型", self.model_input)
        form.addRow("检测间隔", self.poll_interval_input)
        form.addRow("请求超时", self.timeout_input)
        form.addRow("最大回复长度", self.max_reply_input)
        form.addRow("人设称呼", self.persona_name_input)
        form.addRow("双方关系", self.relationship_input)
        form.addRow("回复语气", self.tone_input)
        form.addRow("禁止词", self.forbidden_topics_input)
        outer.addLayout(form)

        buttons = QHBoxLayout()
        save_button = QPushButton("保存设置")
        save_button.clicked.connect(self._save_settings)
        self.diagnose_button = QPushButton("检查环境")
        self.diagnose_button.clicked.connect(self._diagnose_environment)
        buttons.addWidget(save_button)
        buttons.addWidget(self.diagnose_button)
        buttons.addStretch(1)
        outer.addLayout(buttons)
        outer.addStretch(1)
        return page

    def _load_settings_into_ui(self) -> None:
        self.target_name_input.setText(self.settings.target_user_name)
        self.api_key_input.setText(self.settings.api_key)
        self.base_url_input.setText(self.settings.api_base_url)
        self.model_input.setText(self.settings.model)
        self.poll_interval_input.setValue(self.settings.poll_interval_ms)
        self.timeout_input.setValue(self.settings.request_timeout_seconds)
        self.max_reply_input.setValue(self.settings.max_reply_chars)
        self.persona_name_input.setText(self.settings.persona.display_name)
        self.relationship_input.setText(self.settings.persona.relationship)
        self.tone_input.setText(self.settings.persona.tone)
        self.forbidden_topics_input.setText("，".join(self.settings.persona.forbidden_topics))
        self.skill_relationship_input.setText(self.settings.skill_relationship)
        self.skill_style_input.setText(self.settings.skill_style)
        self.skill_goal_input.setText(self.settings.skill_goal)
        self.skill_enabled_checkbox.blockSignals(True)
        self.skill_enabled_checkbox.setChecked(
            self.settings.reply_mode == "goutoujunshi"
        )
        self.skill_enabled_checkbox.blockSignals(False)
        self.auto_start_checkbox.setChecked(self.settings.auto_start)
        self.auto_send_checkbox.setChecked(self.settings.auto_send)
        self._update_bind_button_state()

    def _collect_settings(self) -> AppSettings:
        forbidden = [
            item.strip()
            for item in self.forbidden_topics_input.text().replace(",", "，").split("，")
            if item.strip()
        ]
        return self.settings.model_copy(
            update={
                "target_user_name": self.target_name_input.text().strip(),
                "api_key": self.api_key_input.text(),
                "api_base_url": self.base_url_input.text().strip(),
                "model": self.model_input.text().strip(),
                "poll_interval_ms": self.poll_interval_input.value(),
                "request_timeout_seconds": self.timeout_input.value(),
                "max_reply_chars": self.max_reply_input.value(),
                "reply_mode": (
                    "goutoujunshi"
                    if self.skill_enabled_checkbox.isChecked()
                    else "standard"
                ),
                "skill_relationship": self.skill_relationship_input.text().strip()
                or self.settings.skill_relationship,
                "skill_style": self.skill_style_input.text().strip()
                or self.settings.skill_style,
                "skill_goal": self.skill_goal_input.text().strip()
                or self.settings.skill_goal,
                "auto_start": self.auto_start_checkbox.isChecked(),
                "auto_send": self.auto_send_checkbox.isChecked(),
                "persona": self.settings.persona.model_copy(
                    update={
                        "display_name": self.persona_name_input.text().strip(),
                        "relationship": self.relationship_input.text().strip()
                        or self.settings.persona.relationship,
                        "tone": self.tone_input.text().strip() or self.settings.persona.tone,
                        "forbidden_topics": forbidden,
                    }
                ),
            }
        )

    def _bind_current_chat(self) -> None:
        try:
            settings = self._collect_settings()
            if not settings.target_user_name:
                raise TargetBindingError("请输入目标用户名称")
            self.settings = settings
            self.runtime.update_settings(settings)
            self.bound_window = self.runtime.bind_target(settings.target_user_name)
            self.orchestrator.settings = settings
            self.orchestrator.bind(self.bound_window)
            self._set_state(BotState.READY)
            self._append_log(f"已绑定：{self.bound_window.title}")
            self.settings_store.save(settings)
            self._refresh_context()
        except Exception as exc:
            self._show_error("绑定失败", str(exc))
            self._set_state(BotState.UNBOUND)

    def _start(self) -> None:
        try:
            settings = self._collect_settings()
            self.settings = settings
            self.runtime.update_settings(settings)
            self.orchestrator.settings = settings
            self.orchestrator.start()
            if self.worker is None or not self.worker.isRunning():
                self.worker = EngineWorker(self.orchestrator, settings.poll_interval_ms)
                self.worker.result_ready.connect(self._handle_tick_result)
                self.worker.failed.connect(self._handle_worker_error)
                self.worker.start()
            self._set_state(self.orchestrator.state)
            self._append_log("开始监测。")
        except Exception as exc:
            self._show_error("启动失败", str(exc))

    def _auto_start_if_configured(self) -> None:
        if not self.settings.auto_start or not self.settings.target_user_name:
            return
        try:
            settings = self._collect_settings()
            self.settings = settings
            self.runtime.update_settings(settings)
            self.bound_window = self.runtime.bind_target(settings.target_user_name)
            self.orchestrator.settings = settings
            self.orchestrator.bind(self.bound_window)
            self._set_state(BotState.READY)
            self.settings_store.save(settings)
            self._start()
            self._append_log("已按保存的配置自动绑定并开始。")
        except Exception as exc:
            self._set_state(BotState.UNBOUND)
            self._append_log(f"自动启动失败：{exc}")

    def _pause(self) -> None:
        self.orchestrator.pause()
        self._set_state(self.orchestrator.state)
        self._append_log("已暂停。")

    def _stop(self) -> None:
        self.orchestrator.stop()
        self._stop_worker()
        self._set_state(self.orchestrator.state)
        self._append_log("已停止。")

    def _emergency_stop(self) -> None:
        self.orchestrator.emergency_stop()
        self.auto_send_checkbox.setChecked(False)
        self._stop_worker()
        self._set_state(self.orchestrator.state)
        self._append_log("急停：自动发送已关闭。")

    def _stop_worker(self) -> None:
        if self.worker is None:
            return
        self.worker.request_stop()
        self.worker.wait(3000)
        self.worker = None

    def _toggle_auto_send(self, enabled: bool) -> None:
        self.settings.auto_send = enabled
        self.orchestrator.settings.auto_send = enabled
        try:
            self.settings_store.save(self.settings)
        except Exception as exc:
            logger.exception("Failed to persist auto-send setting")
            self._show_error("保存失败", f"无法保存自动发送设置：{exc}")
        self._append_log("自动发送已开启。" if enabled else "自动发送已关闭。")

    def _toggle_auto_start(self, enabled: bool) -> None:
        self.settings.auto_start = enabled
        try:
            self.settings_store.save(self.settings)
        except Exception as exc:
            logger.exception("Failed to persist auto-start setting")
            self._show_error("保存失败", f"无法保存自动启动设置：{exc}")
        self._append_log("启动后自动开始已开启。" if enabled else "启动后自动开始已关闭。")

    def _toggle_skill_mode(self, enabled: bool) -> None:
        settings = self._collect_settings()
        self.settings = settings
        self.runtime.update_settings(settings)
        self.orchestrator.settings = settings
        self.settings_store.save(settings)
        self._append_log("狗头军师模式已开启。" if enabled else "已切回普通模式。")

    def _analyze_with_skill(self) -> None:
        if self.skill_analysis_worker is not None and self.skill_analysis_worker.isRunning():
            return
        messages = self.runtime.storage.recent_messages(
            self.settings.context_recent_messages
        )
        if not messages:
            self._show_error("无法分析", "当前没有可用于分析的上下文。")
            return
        self.skill_analyze_button.setEnabled(False)
        self.skill_status_label.setText("正在分析当前上下文…")
        worker = SkillAnalysisWorker(self.runtime.generator, messages)
        worker.result_ready.connect(self._handle_skill_analysis)
        worker.failed.connect(self._handle_skill_error)
        worker.finished.connect(lambda: self.skill_analyze_button.setEnabled(True))
        self.skill_analysis_worker = worker
        worker.start()

    def _handle_skill_analysis(self, result: object) -> None:
        self._rendered_skill_result = result
        self._render_skill_result(result)
        self.skill_status_label.setText("分析完成；可人工核对后填入草稿。")

    def _handle_skill_error(self, message: str) -> None:
        self.skill_status_label.setText("分析失败")
        self._show_error("狗头军师分析失败", message)

    def _render_skill_result(self, result: object) -> None:
        candidates = list(getattr(result, "candidates", []))
        best_index = int(getattr(result, "best_index", 0) or 0)
        summary_lines = [
            f"情绪承接：{getattr(result, 'support', '')}",
            f"事实：{'；'.join(getattr(result, 'facts', []))}",
            f"推测：{'；'.join(getattr(result, 'hypotheses', []))}",
            f"未知：{'；'.join(getattr(result, 'unknowns', []))}",
            f"建议：{getattr(result, 'recommendation', '')}",
            f"下一步：{getattr(result, 'next_step', '')}",
            f"停止条件：{getattr(result, 'stop_condition', '')}",
        ]
        self.skill_summary_output.setPlainText("\n".join(summary_lines))
        self.skill_candidates_table.setRowCount(len(candidates))
        for row, candidate in enumerate(candidates):
            marker = "★ " if row == best_index else ""
            values = [
                marker + str(getattr(candidate, "text", "")),
                str(getattr(candidate, "reason", "")),
                str(getattr(candidate, "tradeoff", "")),
            ]
            for column, value in enumerate(values):
                self.skill_candidates_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        if candidates:
            self.skill_candidates_table.selectRow(
                min(max(best_index, 0), len(candidates) - 1)
            )
            self.skill_candidates_table.resizeColumnsToContents()
            self.skill_candidates_table.horizontalHeader().setStretchLastSection(True)

    def _fill_selected_skill_candidate(self) -> None:
        row = self.skill_candidates_table.currentRow()
        if row < 0:
            self._show_error("无法填入", "请先选择一条候选回复。")
            return
        item = self.skill_candidates_table.item(row, 0)
        if item is None or not item.text().strip():
            self._show_error("无法填入", "当前候选为空。")
            return
        text = item.text().removeprefix("★ ").strip()
        if self.skill_fill_worker is not None and self.skill_fill_worker.isRunning():
            return
        self.skill_fill_button.setEnabled(False)
        self.skill_status_label.setText("正在写入 QQ 输入框…")
        worker = SkillFillWorker(self.runtime.sender, text)
        worker.finished_ok.connect(self._handle_skill_fill_ok)
        worker.failed.connect(self._handle_skill_error)
        worker.finished.connect(lambda: self.skill_fill_button.setEnabled(True))
        self.skill_fill_worker = worker
        worker.start()

    def _handle_skill_fill_ok(self, text: str) -> None:
        self.skill_status_label.setText("草稿已写入 QQ 输入框，确认后手动发送。")
        self._append_log(f"狗头军师草稿已填入：{text}")

    def _save_settings(self) -> None:
        try:
            settings = self._collect_settings()
            self.settings = settings
            self.runtime.update_settings(settings)
            self.orchestrator.settings = settings
            self.settings_store.save(settings)
            self._append_log("设置已保存。")
        except Exception as exc:
            self._show_error("保存失败", str(exc))

    def _diagnose_environment(self) -> None:
        try:
            window_count = len(self.runtime.window_provider.list_windows())
        except Exception as exc:
            window_count = -1
            window_error = str(exc)
        else:
            window_error = ""
        data_dir = self.runtime.storage.path.parent
        lines = [
            f"Python 环境：{sys.version.split()[0]}",
            f"QQ 客户端窗口数：{window_count}",
            f"目标名称：{'已填写' if self.target_name_input.text().strip() else '未填写'}",
            f"DeepSeek API Key：{'已填写' if self.api_key_input.text().strip() else '未填写'}",
            f"Base URL：{self.base_url_input.text().strip()}",
            f"模型：{self.model_input.text().strip()}",
            f"数据目录：{data_dir}",
            f"数据目录可写：{'是' if data_dir.exists() or data_dir.parent.exists() else '否'}",
        ]
        if window_error:
            lines.append(f"窗口检查错误：{window_error}")
        QMessageBox.information(self, "环境检查", "\n".join(lines))

    def _handle_tick_result(self, result: TickResult) -> None:
        self._set_state(result.state)
        if result.message:
            self._append_log(result.message)
        if result.event is not None:
            self.event_label.setText(
                f"{datetime.now():%H:%M:%S}  {result.kind.value}: "
                f"{result.event.text[:160]}"
            )
        if result.reply is not None:
            self._append_log(f"回复草稿：{result.reply}")
        if result.context:
            self._render_context(result.context)
        last_skill = getattr(self.runtime.generator, "last_skill_result", None)
        if last_skill is not None and last_skill is not self._rendered_skill_result:
            self._rendered_skill_result = last_skill
            self._render_skill_result(last_skill)

    def _handle_worker_error(self, message: str) -> None:
        self._show_error("运行错误", message)

    def _refresh_context(self) -> None:
        messages = self.runtime.storage.recent_messages(self.settings.context_recent_messages)
        self._render_context(messages)

    def _render_context(self, messages: list[object]) -> None:
        lines: list[str] = []
        for message in messages:
            role = getattr(message, "role", "unknown")
            text = getattr(message, "text", "")
            label = {"user": "对方", "assistant": "回复"}.get(role, role)
            lines.append(f"{label}: {text}")
        self.context_output.setPlainText("\n".join(lines))

    def _save_context(self) -> None:
        messages = []
        now = time.time()
        for index, raw_line in enumerate(self.context_output.toPlainText().splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("对方:"):
                role = "user"
                text = line.removeprefix("对方:").strip()
            elif line.startswith("回复:"):
                role = "assistant"
                text = line.removeprefix("回复:").strip()
            else:
                self._show_error("上下文格式错误", f"无法识别行：{line}")
                return
            messages.append(
                ChatMessage(
                    role=role,
                    text=text,
                    source="manual",
                    confidence=None,
                    timestamp=now + index,
                )
            )
        self.runtime.storage.replace_messages(messages)
        self._append_log("上下文已更新。")
        self._refresh_context()

    def _clear_context(self) -> None:
        answer = QMessageBox.question(
            self,
            "清空上下文",
            "确认清空当前对话上下文？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.runtime.storage.clear_messages()
            self.runtime.storage.set_state("context_cleared_at", datetime.now().isoformat())
            self._refresh_context()
            self._append_log("上下文已清空。")

    def _set_state(self, state: BotState) -> None:
        self.state_label.setText(state.value)
        self.statusBar().showMessage(state.value)
        running = state in {
            BotState.READY,
            BotState.MONITORING,
            BotState.GENERATING,
            BotState.SENDING,
        }
        self.bind_button.setEnabled(
            not running and bool(self.target_name_input.text().strip())
        )
        self.start_button.setEnabled(
            state in {BotState.READY, BotState.PAUSED, BotState.STOPPED}
            and self.bound_window is not None
        )
        self.pause_button.setEnabled(
            state in {BotState.MONITORING, BotState.GENERATING, BotState.SENDING}
        )

    def _update_bind_button_state(self) -> None:
        if not hasattr(self, "bind_button"):
            return
        running = self.orchestrator.state in {
            BotState.READY,
            BotState.MONITORING,
            BotState.GENERATING,
            BotState.SENDING,
        }
        self.bind_button.setEnabled(
            bool(self.target_name_input.text().strip()) and not running
        )

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")
        logger.info(message)

    def _show_error(self, title: str, message: str) -> None:
        self._append_log(f"{title}: {message}")
        QMessageBox.critical(self, title, message)

    def closeEvent(self, event: object) -> None:
        self._stop_worker()
        event.accept()


def run_gui() -> int:
    app = QApplication.instance() or QApplication([])
    _configure_font(app)
    window = MainWindow()
    window.show()
    return app.exec()


def _configure_font(app: QApplication) -> None:
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyh.ttf"),
    ):
        if not candidate.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(candidate))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
            return
    app.setFont(QFont("Microsoft YaHei UI", 10))
