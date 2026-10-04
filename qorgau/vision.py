from pathlib import Path
import math
import time
import cv2
import numpy as np
from .engine import Observation


class YoloDetector:
    """YOLO11n raw ONNX COCO output; class-aware NMS for person and cell phone."""
    def __init__(self, model: Path, confidence: float, phone_confidence: float = 0.25):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.size = int(shape[2])
        self.confidence = confidence
        self.phone_confidence = phone_confidence

    def detect(self, frame):
        h, w = frame.shape[:2]
        scale = self.size / max(h, w)
        resized_w, resized_h = round(w * scale), round(h * scale)
        left, top = (self.size - resized_w) // 2, (self.size - resized_h) // 2
        image = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        image[top:top+resized_h, left:left+resized_w] = cv2.resize(frame, (resized_w, resized_h))
        tensor = np.ascontiguousarray(image[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        raw = self.session.run(None, {self.input_name: tensor})[0]
        predictions = raw[0].T
        if predictions.shape[1] != 84:
            raise RuntimeError(f"Ожидался YOLO11 COCO [1,84,N], получено {raw.shape}")
        best_classes = predictions[:, 4:].argmax(axis=1)
        boxes = []
        for class_id, name in ((0, "person"), (67, "phone")):
            threshold = self.phone_confidence if class_id == 67 else self.confidence
            scores = predictions[:, 4 + class_id]
            mask = (scores >= threshold) & (best_classes == class_id)
            candidates = predictions[mask, :4].copy()
            confidences = scores[mask]
            if not len(candidates):
                continue
            candidates[:, 0] = (candidates[:, 0] - candidates[:, 2] / 2 - left) / scale
            candidates[:, 1] = (candidates[:, 1] - candidates[:, 3] / 2 - top) / scale
            candidates[:, 2:] /= scale
            indices = cv2.dnn.NMSBoxes(candidates.tolist(), confidences.tolist(), threshold, 0.45)
            for index in np.asarray(indices).reshape(-1):
                x, y, bw, bh = candidates[index]
                x1, y1 = max(0, int(x)), max(0, int(y))
                x2, y2 = min(w, int(x+bw)), min(h, int(y+bh))
                if x2 > x1 and y2 > y1:
                    boxes.append((name, float(confidences[index]), (x1, y1, x2, y2)))
        return boxes


class VisionPipeline:
    def __init__(self, model_directory: Path, confidence: float, phone_confidence: float = 0.25):
        import mediapipe as mp
        self.mp = mp
        for filename in ("yolo11n.onnx", "face_landmarker.task"):
            if not (model_directory / filename).is_file():
                raise FileNotFoundError(f"Нет модели {filename}. Выполните scripts/prepare_models.py перед сборкой.")
        self.yolo = YoloDetector(model_directory / "yolo11n.onnx", confidence, phone_confidence)
        options = mp.tasks.vision.FaceLandmarkerOptions(
            # Buffer also supports non-ASCII Windows checkout paths in native MediaPipe.
            base_options=mp.tasks.BaseOptions(model_asset_buffer=(model_directory / "face_landmarker.task").read_bytes()),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=3, output_facial_transformation_matrixes=True)
        self.face = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self.last_timestamp = -1

    def analyze(self, frame, timestamp_ms):
        started = time.perf_counter()
        boxes = self.yolo.detect(frame)
        timestamp_ms = max(self.last_timestamp + 1, timestamp_ms)
        self.last_timestamp = timestamp_ms
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = self.face.detect_for_video(image, timestamp_ms)
        yaw = None
        if len(result.face_landmarks) == 1 and result.facial_transformation_matrixes:
            rotation = np.asarray(result.facial_transformation_matrixes[0])[:3, :3]
            # Normalize scaled matrix columns before extracting yaw about vertical axis.
            rotation = rotation / np.maximum(np.linalg.norm(rotation, axis=0), 1e-9)
            yaw = math.degrees(math.atan2(rotation[0, 2], rotation[2, 2]))
        return Observation(people=sum(b[0] == "person" for b in boxes),
            phones=sum(b[0] == "phone" for b in boxes), faces=len(result.face_landmarks),
            yaw=yaw, boxes=boxes, inference_ms=(time.perf_counter()-started)*1000)

    def close(self):
        self.face.close()


def annotate(frame, observation):
    image = frame.copy()
    for name, confidence, (x1, y1, x2, y2) in observation.boxes:
        color = (92, 211, 161) if name == "person" else (80, 173, 255)
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, f"{name} {confidence:.0%}", (x1, max(18, y1-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return image
