from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def data_root() -> Path:
    override = os.environ.get("QORGAU_DATA_DIR")
    root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "QorgauAI"
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class Settings:
    camera_index: int = 0
    confidence: float = 0.45
    phone_confidence: float = 0.25
    absence_seconds: float = 5.0
    multiple_seconds: float = 2.0
    phone_seconds: float = 1.5
    head_seconds: float = 3.0
    window_seconds: float = 0.0
    head_angle: float = 30.0
    save_evidence: bool = False

    @classmethod
    def load(cls, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            settings = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            settings.validate()
            return settings
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def validate(self):
        if not isinstance(self.camera_index, int) or not 0 <= self.camera_index <= 9:
            raise ValueError("Номер камеры должен быть от 0 до 9")
        if not 0.1 <= self.confidence <= 0.95 or not 0.1 <= self.phone_confidence <= 0.95 or not 10 <= self.head_angle <= 80:
            raise ValueError("Некорректная уверенность или угол")
        for key in ("absence_seconds", "multiple_seconds", "phone_seconds", "head_seconds"):
            if not 0.5 <= getattr(self, key) <= 60:
                raise ValueError("Порог должен быть от 0.5 до 60 секунд")
        if not 0 <= self.window_seconds <= 60:
            raise ValueError("Задержка окна должна быть от 0 до 60 секунд")
        if not isinstance(self.save_evidence, bool):
            raise ValueError("Некорректное значение сохранения кадров")

    def save(self, path: Path):
        self.validate()
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temporary.replace(path)
