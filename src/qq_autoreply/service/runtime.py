from __future__ import annotations

from dataclasses import dataclass

from ..automation.input import DesktopReplySender
from ..automation.uia_chat import UiaChatReader
from ..config import AppSettings, project_root
from ..deepseek import DeepSeekReplyGenerator
from ..domain import QQWindowInfo
from ..goutoujunshi import GoutoujunshiGenerator, SwitchableReplyGenerator
from ..storage import Storage
from ..text import normalize_text
from ..vision.uia_detector import UiaMessageDetector
from ..vision.windows import Win32WindowProvider


class TargetBindingError(RuntimeError):
    pass


@dataclass(slots=True)
class Runtime:
    settings: AppSettings
    storage: Storage
    window_provider: Win32WindowProvider
    detector: UiaMessageDetector
    generator: SwitchableReplyGenerator
    sender: DesktopReplySender

    @classmethod
    def create(cls, settings: AppSettings) -> Runtime:
        storage = Storage(project_root() / "data" / "qq-autoreply.sqlite3")
        window_provider = Win32WindowProvider()
        detector = UiaMessageDetector(
            settings=settings,
            reader=UiaChatReader(),
            window_provider=window_provider,
        )
        standard_generator = DeepSeekReplyGenerator(settings)
        skill_generator = GoutoujunshiGenerator(settings)
        generator = SwitchableReplyGenerator(
            settings=settings,
            standard=standard_generator,
            skill=skill_generator,
        )
        sender = DesktopReplySender(
            settings=settings,
            detector=detector,
            window_provider=window_provider,
        )
        return cls(
            settings=settings,
            storage=storage,
            window_provider=window_provider,
            detector=detector,
            generator=generator,
            sender=sender,
        )

    def bind_target(self, target_name: str) -> QQWindowInfo:
        target_name = target_name.strip()
        if not target_name:
            raise TargetBindingError("Target user name is required")

        windows = self.window_provider.list_windows()
        if not windows:
            raise TargetBindingError("No visible QQ desktop window found")

        foreground = self.window_provider.foreground_handle()
        ordered = sorted(windows, key=lambda window: window.handle != foreground)
        errors: list[str] = []
        for window in ordered:
            self.settings.target_user_name = target_name
            self.detector.bind(window)
            validation = self.detector.validate_target()
            if validation is None:
                previous_target = self.storage.get_state("bound_target")
                if previous_target and previous_target != target_name:
                    self.storage.clear_messages()
                    self.storage.clear_events()
                if not self.storage.recent_messages(1):
                    self.storage.replace_messages(self.detector.read_visible_history())
                self.storage.set_state("bound_target", target_name)
                return window
            errors.append(f"{window.title}: {validation.reason}")

        detail = "; ".join(errors)
        raise TargetBindingError(f"Target name did not match visible QQ header. {detail}")

    def update_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.detector.settings = settings
        self.generator.configure(settings)
        self.sender.settings = settings


def normalized_title_contains(observed_title: str, target_name: str) -> bool:
    return normalize_text(target_name) in normalize_text(observed_title)
