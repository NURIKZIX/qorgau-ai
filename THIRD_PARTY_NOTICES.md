# Third-party notices

QORGAU AI source is distributed under AGPL-3.0; see LICENSE. Preserve upstream notices with redistribution.

| Component | Upstream / license reference |
|---|---|
| Ultralytics YOLO11n pretrained COCO weights, exported to ONNX | https://github.com/ultralytics/ultralytics/blob/main/LICENSE ; AGPL-3.0 / Ultralytics enterprise license |
| MediaPipe Python + Face Landmarker model asset | https://github.com/google-ai-edge/mediapipe ; upstream Apache-2.0 notices and model source in models/manifest.json |
| Qt for Python / PySide6 / Shiboken6 | https://doc.qt.io/qtforpython-6/licenses.html ; LGPL-3.0 / GPL / commercial terms per component |
| OpenCV | https://github.com/opencv/opencv/blob/4.x/LICENSE ; Apache-2.0 |
| ONNX Runtime | https://github.com/microsoft/onnxruntime/blob/main/LICENSE ; MIT |
| NumPy | https://github.com/numpy/numpy/blob/main/LICENSE.txt ; BSD-3-Clause and bundled library notices |
| Python | https://docs.python.org/3/license.html ; PSF license and included notices |
| Microsoft Visual C++ runtime DLLs distributed with the Qt wheel | https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files ; Microsoft redistributable component terms |
| PyInstaller bootloader | https://pyinstaller.org/en/stable/license.html ; GPL with bootloader exception |

Dependencies retain their own licenses; the build collects MediaPipe and ONNX Runtime package data. Installed wheels contain additional transitive dependency notices. This application uses YOLO11n, not the model featured by the changing current default of the Ultralytics export documentation. Its name, hashes and export settings are recorded in the model manifest.
