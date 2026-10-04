"""Run with .export-venv Python after installing CPU torch + ultralytics + onnx."""
import hashlib
import importlib.metadata
import os
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
SOURCES = {
    "yolo11n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}


def download(url, destination):
    if destination.exists():
        return
    print(f"Downloading {destination.name}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "QorgauAI-model-setup/1.0"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as stream:
        shutil.copyfileobj(response, stream)
    temporary.replace(destination)


def main():
    MODELS.mkdir(exist_ok=True)
    for filename, url in SOURCES.items():
        download(url, MODELS / filename)
    if not (MODELS / "yolo11n.onnx").exists():
        config_directory = ROOT / ".cache" / "ultralytics"
        config_directory.mkdir(parents=True, exist_ok=True)
        os.environ["YOLO_CONFIG_DIR"] = str(config_directory)
        from ultralytics import YOLO
        YOLO(str(MODELS / "yolo11n.pt")).export(format="onnx", imgsz=640, opset=17, simplify=False, dynamic=False, nms=False, device="cpu")
    manifest = {name: {"sha256": hashlib.sha256((MODELS/name).read_bytes()).hexdigest(),
                       "bytes": (MODELS/name).stat().st_size} for name in ("yolo11n.onnx", "face_landmarker.task")}
    (MODELS / "manifest.json").write_text(json.dumps({"models": manifest, "sources": SOURCES,
        "original_pt_sha256": hashlib.sha256((MODELS/"yolo11n.pt").read_bytes()).hexdigest(),
        "exporter_versions": {name: importlib.metadata.version(name) for name in ("ultralytics", "torch", "onnx")},
        "export": "YOLO11n COCO, float32, opset17, 640x640, raw output, CPU"}, indent=2), encoding="utf-8")
    print("Models ready", flush=True)


if __name__ == "__main__":
    main()
