import os
from pathlib import Path


def prepare_runtime(root: Path):
    """Preload MediaPipe before Qt installs its optional-feature import hooks."""
    cache = root/"cache"/"matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache)
    os.environ["MPLBACKEND"] = "Agg"
    import mediapipe  # noqa: F401; no model or camera is opened here


def prepare_fonts(app):
    from PySide6.QtGui import QFont, QFontDatabase
    # The Windows offscreen Qt plugin does not enumerate system fonts. Register
    # installed fonts for both diagnostics and consistent packaged rendering.
    directory = Path(os.environ.get("WINDIR", "C:/Windows"))/"Fonts"
    for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisym.ttf"):
        path = directory/filename
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 10))
