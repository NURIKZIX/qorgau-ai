"""Packaged smoke test: native models, UI, all events, DB and reports. No webcam."""
import json
import os
from pathlib import Path
import time
import traceback


def run(output: Path):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QORGAU_DATA_DIR"] = str(output/"data")
    result = {"camera_tested": False}
    window = db = None
    try:
        from .runtime import prepare_fonts, prepare_runtime
        prepare_runtime(output/"data")
        import cv2
        import numpy as np
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication
        from .config import Settings, resource_root
        from .engine import Event, EventEngine, Observation
        from .reports import export_report
        from .storage import Database
        from .ui import MainWindow
        from .vision import VisionPipeline
        from .worker import demo_frame

        pipeline = VisionPipeline(resource_root()/"models", 0.45)
        observation = pipeline.analyze(np.zeros((480, 640, 3), dtype=np.uint8), 0)
        result["models"] = {"people_on_blank": observation.people, "faces_on_blank": observation.faces, "inference_ms": round(observation.inference_ms, 1)}
        pipeline.close()
        assert observation.people == 0 and observation.faces == 0

        app = QApplication.instance() or QApplication([])
        prepare_fonts(app)
        db = Database(output/"diagnostics.sqlite3")
        settings = Settings()
        window = MainWindow(db, settings)
        window.show()
        window.candidate.setText("Демо участник / QA")
        window.exam.setText("Проверка приложения")
        window.mode.setCurrentIndex(1)
        window.connect_button.click()
        loop = QEventLoop()
        QTimer.singleShot(1800, loop.quit)
        loop.exec()
        assert window.worker_ready and window.start_button.isEnabled(), "Demo source did not start"
        window.start_button.click()
        assert window.session_id is not None, "Session did not start"
        session_id = window.session_id
        # Exercise the same UI observation path with an accelerated synthetic clock.
        for step in range(192):
            t = step / 4
            _, observation = demo_frame(t)
            window.session_start = time.monotonic() - t
            window.consume_observation(observation)
        window.tick()
        window.preview.grab().save(str(output/"preview.png"))
        window.grab().save(str(output/"monitor.png"))
        scroll = window.pages.widget(0)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        window.grab().save(str(output/"journal.png"))
        scroll.verticalScrollBar().setValue(0)
        window.stop_button.click()
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()
        events = db.events(session_id)
        result["events"] = [e["kind"] for e in events]
        assert set(result["events"]) == {"phone", "multiple", "absence", "head", "window"}, result["events"]
        assert all(e["end"] is not None for e in events)
        window.navigate(1)
        window.selected_session = session_id
        window.refresh_sessions()
        window.review_table.selectRow(0)
        window.review_event("dismissed")
        assert db.events(session_id)[0]["review"] == "dismissed"
        window.note.setPlainText("Демонстрационная проверка. Не реальный экзамен.")
        window.save_note()
        for suffix in ("html", "csv", "json"):
            export_report(db, session_id, output/f"exam-report.{suffix}")
        window.grab().save(str(output/"sessions.png"))
        window.navigate(2)
        window.grab().save(str(output/"settings.png"))
        window.navigate(0)
        window.resize(1000, 740)
        app.processEvents()
        window.grab().save(str(output/"compact.png"))
        window.search.setText("no-such-candidate")
        window.refresh_sessions()
        assert window.sessions_table.rowCount() == 0
        # Exercise failure handling through the application controller as well.
        window.connect_camera()
        loop = QEventLoop()
        QTimer.singleShot(1200, loop.quit)
        loop.exec()
        window.start_session()
        failure_session = window.session_id
        assert failure_session is not None
        window.on_failure("Синтетическая потеря камеры / диагностическая проверка")
        loop = QEventLoop()
        QTimer.singleShot(300, loop.quit)
        loop.exec()
        assert db.session(failure_session)["status"] == "interrupted"
        technical_events = db.events(failure_session)
        assert {e["kind"] for e in technical_events} == {"camera", "system"}
        assert all(e["end"] is not None for e in technical_events)
        assert window.metrics[2].text() == "0 / 100"
        result["failure_recovery"] = True
        window.close()
        result["ok"] = True
    except Exception:
        result["ok"] = False
        result["error"] = traceback.format_exc()
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel.GetModuleHandleW.restype = wintypes.HMODULE
            kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
            result["native_libraries"] = {}
            for name in ("python3.dll", "python312.dll", "Qt6Core.dll", "pyside6.abi3.dll", "shiboken6.abi3.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
                handle = kernel.GetModuleHandleW(name)
                if handle:
                    path = ctypes.create_unicode_buffer(32768)
                    kernel.GetModuleFileNameW(handle, path, len(path))
                    result["native_libraries"][name] = path.value
    finally:
        if window is not None and window.worker is not None:
            window.worker.requestInterruption()
            window.worker.wait(10000)
        if db is not None:
            db.close()
    (output/"result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
