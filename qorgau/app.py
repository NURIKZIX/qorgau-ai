import argparse
import logging
from pathlib import Path
import sys
import traceback
from .config import Settings, data_root
from .storage import Database


def main():
    parser = argparse.ArgumentParser(description="QORGAU AI exam monitor")
    parser.add_argument("--self-test", type=Path, metavar="OUTPUT_DIR", help="Run packaged diagnostics without a camera")
    parser.add_argument("--demo", action="store_true", help="Open explicitly marked demo preview")
    args = parser.parse_args()
    if args.self_test:
        from .diagnostics import run
        return run(args.self_test)
    from .runtime import prepare_fonts, prepare_runtime
    prepare_runtime(data_root())
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .ui import MainWindow
    app = QApplication(sys.argv[:1])
    prepare_fonts(app)
    app.setApplicationName("QORGAU AI")
    root = data_root()
    logging.basicConfig(filename=str(root/"application.log"), level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    lock = QLockFile(str(root/"application.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "QORGAU AI", "Приложение уже запущено.")
        return 1
    def handle_exception(kind, value, tb):
        message = "".join(traceback.format_exception(kind, value, tb))
        logging.error(message)
        QMessageBox.critical(None, "Ошибка QORGAU AI", f"{value}\nДиагностика сохранена в {root / 'application.log'}")
    sys.excepthook = handle_exception
    db = Database(root/"qorgau.sqlite3")
    db.recover()
    window = MainWindow(db, Settings.load(root/"settings.json"))
    window.show()
    if args.demo:
        window.launch_demo()
    try:
        return app.exec()
    finally:
        db.close()
        lock.unlock()
