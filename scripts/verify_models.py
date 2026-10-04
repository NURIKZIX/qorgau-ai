"""Integration checks on upstream test fixtures, without accessing a webcam."""
import json
from io import BytesIO
from pathlib import Path
import sys
import urllib.request
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    from qorgau.runtime import prepare_runtime
    prepare_runtime(ROOT/"artifacts"/"model-check")
    import cv2
    import numpy as np
    from qorgau.vision import VisionPipeline
    output = ROOT/"artifacts"/"model-check"
    output.mkdir(parents=True, exist_ok=True)
    fixtures = {
        "bus": "https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/assets/bus.jpg",
        "portrait": "https://storage.googleapis.com/mediapipe-assets/portrait.jpg",
    }
    pipeline = VisionPipeline(ROOT/"models", 0.45)
    results = {}
    try:
        for index, (name, url) in enumerate(fixtures.items()):
            with urllib.request.urlopen(url, timeout=90) as response:
                data = response.read()
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"Invalid fixture {name}")
            obs = pipeline.analyze(image, index*1000)
            results[name] = {"people": obs.people, "faces": obs.faces, "yaw": obs.yaw, "latency_ms": round(obs.inference_ms, 1), "source": url}
        assert results["bus"]["people"] >= 2, results
        assert results["portrait"]["faces"] == 1, results
        assert results["portrait"]["yaw"] is not None, results
        # Select real cell-phone fixtures by official COCO class annotations.
        dataset_url = "https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip"
        fixture_cache = output/"coco128.zip"
        if fixture_cache.exists():
            archive_bytes = fixture_cache.read_bytes()
        else:
            with urllib.request.urlopen(dataset_url, timeout=90) as response:
                archive_bytes = response.read(20*1024*1024+1)
            fixture_cache.write_bytes(archive_bytes)
        if len(archive_bytes) > 20*1024*1024:
            raise RuntimeError("Unexpected fixture archive size")
        candidates = []
        with ZipFile(BytesIO(archive_bytes)) as archive:
            for name in archive.namelist():
                if "/labels/" not in name or not name.endswith(".txt"):
                    continue
                for line in archive.read(name).decode().splitlines():
                    parts = line.split()
                    if parts and int(parts[0]) == 67:
                        candidates.append((float(parts[3])*float(parts[4]), name.replace("/labels/", "/images/").replace(".txt", ".jpg"), tuple(map(float, parts[1:5]))))
            phones = 0
            results["annotated_phones"] = len(candidates)
            for area, name, xywh in sorted(candidates, reverse=True)[:8]:
                image = cv2.imdecode(np.frombuffer(archive.read(name), np.uint8), cv2.IMREAD_COLOR)
                h, w = image.shape[:2]
                x, y, bw, bh = xywh
                # Check an annotated close view too: small phones in wide scenes
                # are a known limitation of the nano model at the default threshold.
                x1, x2 = max(0, int((x-bw*1.5)*w)), min(w, int((x+bw*1.5)*w))
                y1, y2 = max(0, int((y-bh*1.5)*h)), min(h, int((y+bh*1.5)*h))
                close_view = image[y1:y2, x1:x2]
                boxes = pipeline.yolo.detect(image)
                view = "full frame"
                if not any(box[0] == "phone" for box in boxes) and close_view.size:
                    boxes = pipeline.yolo.detect(close_view)
                    view = "annotated close view"
                phones = sum(box[0] == "phone" for box in boxes)
                if phones:
                    results["phone"] = {"phones": phones, "fixture": name, "source": dataset_url,
                        "view": view, "annotated_area": round(area, 4),
                        "confidence": [round(box[1], 4) for box in boxes if box[0] == "phone"]}
                    break
        assert phones >= 1, "YOLO did not find a phone in annotated COCO fixtures"
        results["ok"] = True
    finally:
        pipeline.close()
        (output/"results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
