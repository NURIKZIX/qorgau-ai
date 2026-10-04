# Model assets

Run `scripts/prepare_models.py` using the export environment described in the root README. The Windows build includes `yolo11n.onnx` and `face_landmarker.task`; it performs no downloads at runtime.

- YOLO11n COCO: https://docs.ultralytics.com/models/yolo11/
- ONNX export: https://docs.ultralytics.com/modes/export/
- Face Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python

`manifest.json` records the asset sources and SHA-256 hashes. YOLO11n assets are provided under Ultralytics AGPL-3.0 terms (or their commercial license); MediaPipe code is Apache-2.0. Preserve the applicable upstream licenses when redistributing.
