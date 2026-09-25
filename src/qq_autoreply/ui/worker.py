from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from ..service.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


class EngineWorker(QThread):
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, orchestrator: Orchestrator, interval_ms: int) -> None:
        super().__init__()
        self.orchestrator = orchestrator
        self.interval_ms = interval_ms
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        while not self._stop_requested:
            try:
                result = self.orchestrator.tick()
                self.result_ready.emit(result)
            except Exception as exc:
                self.orchestrator.pause()
                logger.exception("Engine worker failed")
                self.failed.emit(str(exc))
            self.msleep(self.interval_ms)


class SkillAnalysisWorker(QThread):
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, generator: object, messages: list[object]) -> None:
        super().__init__()
        self.generator = generator
        self.messages = messages

    def run(self) -> None:
        try:
            result = self.generator.skill.analyze(self.messages)
            self.result_ready.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class SkillFillWorker(QThread):
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, sender: object, text: str) -> None:
        super().__init__()
        self.sender = sender
        self.text = text

    def run(self) -> None:
        try:
            self.sender.fill(self.text)
            self.finished_ok.emit(self.text)
        except Exception as exc:
            self.failed.emit(str(exc))
