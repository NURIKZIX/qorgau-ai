import time
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from .config import resource_root
from .engine import Observation


class CameraWorker(QThread):
    frame = Signal(QImage, object, object)
    status = Signal(str)
    failed = Signal(str)
    ready = Signal()

    def __init__(self, settings, demo=False):
        super().__init__()
        self.settings, self.demo = settings, demo

    def run(self):
        capture = pipeline = None
        try:
            if self.demo:
                self.ready.emit()
                started = time.monotonic()
                while not self.isInterruptionRequested():
                    elapsed = time.monotonic() - started
                    image, observation = demo_frame(elapsed)
                    self.emit_frame(image, observation)
                    self.msleep(100)
                return
            from .vision import VisionPipeline
            self.status.emit("Загрузка YOLO11n и MediaPipe…")
            pipeline = VisionPipeline(resource_root() / "models", self.settings.confidence, self.settings.phone_confidence)
            if self.isInterruptionRequested():
                return
            self.status.emit("Подключение камеры…")
            capture = cv2.VideoCapture(self.settings.camera_index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(self.settings.camera_index)
            if not capture.isOpened():
                raise RuntimeError("Не удалось открыть камеру. Проверьте номер камеры и разрешение Windows; закройте приложения, использующие камеру.")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.ready.emit()
            failures = 0
            while not self.isInterruptionRequested():
                cycle = time.monotonic()
                ok, frame = capture.read()
                if not ok:
                    failures += 1
                    self.frame.emit(QImage(), Observation(camera_ok=False), None)
                    if failures >= 15:
                        raise RuntimeError("Поток камеры потерян. Сессия прервана; подключите камеру и начните новую сессию.")
                    self.msleep(200)
                    continue
                failures = 0
                observation = pipeline.analyze(frame, int(time.monotonic()*1000))
                self.emit_frame(frame, observation)
                delay = max(0, int((0.15 - (time.monotonic()-cycle))*1000))
                self.msleep(delay)
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            if capture is not None:
                capture.release()
            if pipeline is not None:
                pipeline.close()

    def emit_frame(self, frame, observation):
        from .vision import annotate
        display = cv2.cvtColor(annotate(frame, observation), cv2.COLOR_BGR2RGB)
        h, w = display.shape[:2]
        image = QImage(display.data, w, h, display.strides[0], QImage.Format.Format_RGB888).copy()
        self.frame.emit(image, observation, frame)


def demo_frame(elapsed):
    """Explicit synthetic demo that never loads the camera or ML models."""
    phase = int(elapsed) % 48
    people, phones, yaw = 1, 0, 0.0
    if 6 <= phase < 12:
        phones = 1
    elif 14 <= phase < 20:
        people = 2
    elif 22 <= phase < 30:
        people = 0
    elif 32 <= phase < 39:
        yaw = 42.0
    window = 41 <= phase < 46
    frame = np.full((480, 640, 3), (43, 56, 53), dtype=np.uint8)
    for x in range(0, 640, 40):
        cv2.line(frame, (x, 0), (x, 480), (51, 65, 62), 1)
    for y in range(0, 480, 40):
        cv2.line(frame, (0, y), (640, y), (51, 65, 62), 1)
    boxes = []
    for i in range(people):
        x = 220 if i == 0 else 455
        cv2.circle(frame, (x+60, 160), 43, (143, 175, 161), -1)
        cv2.ellipse(frame, (x+60, 350), (82, 130), 0, 180, 360, (101, 132, 120), -1)
        boxes.append(("person", 0.96, (x-25, 105, x+145, 400)))
    if phones:
        cv2.rectangle(frame, (362, 258), (401, 333), (170, 200, 230), -1)
        boxes.append(("phone", 0.91, (355, 250, 409, 340)))
    cv2.putText(frame, "DEMO / SYNTHETIC INPUT", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (160, 221, 246), 2)
    cv2.putText(frame, f"Scenario loop: {phase:02d} / 48s", (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 191, 180), 1)
    return frame, Observation(people=people, phones=phones, faces=people, yaw=yaw,
                            window_away=window, boxes=boxes, inference_ms=0)
