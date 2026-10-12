from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_metrics(model: Any, dataset: Path, imgsz: int, batch: int, device: str) -> dict[str, float]:
    test_images = sorted((dataset.parent / "images" / "test").glob("*"))
    if not test_images:
        raise RuntimeError("test_images_missing")
    absolute_errors: list[float] = []
    relative_errors: list[float] = []
    evaluated = 0
    predictions = model.predict(source=[str(path) for path in test_images], imgsz=imgsz, batch=batch, device=device, stream=True, verbose=False)
    for image, prediction in zip(test_images, predictions):
        label_path = dataset.parent / "labels" / "test" / f"{image.stem}.txt"
        expected = len(label_path.read_text(encoding="utf-8").splitlines()) if label_path.is_file() else 0
        predicted = len(prediction.boxes) if prediction.boxes is not None else 0
        absolute_errors.append(abs(float(predicted - expected)))
        if expected:
            relative_errors.append(abs(float(predicted - expected)) / expected)
        evaluated += 1
    return {
        "count_mae": statistics.fmean(absolute_errors),
        "count_relative_median": statistics.median(relative_errors) if relative_errors else 0.0,
        "count_coverage": evaluated / len(test_images),
    }


def train(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise RuntimeError("ultralytics_required_for_research_baseline") from error
    dataset = Path(args.dataset).resolve()
    project = Path(args.project).resolve()
    project.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.weights)
    result = model.train(
        data=str(dataset),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=0,
        project=str(project),
        name=args.name,
        exist_ok=True,
        pretrained=True,
        verbose=False,
    )
    run_dir = project / args.name
    artifact = run_dir / "weights" / "best.pt"
    if not artifact.is_file():
        raise RuntimeError(f"trained_artifact_missing:{artifact}")
    metrics = model.val(data=str(dataset), imgsz=args.imgsz, batch=args.batch, device=args.device, workers=0, verbose=False)
    count_metrics = _count_metrics(model, dataset, args.imgsz, args.batch, args.device)
    report = {
        "status": "candidate",
        "license_gate": "Ultralytics AGPL-3.0 or enterprise license required before commercial production use",
        "dataset": str(dataset),
        "weights": args.weights,
        "artifact": str(artifact),
        "artifact_sha256": _sha256(artifact),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "device": args.device,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "box_map50": float(metrics.box.map50),
            "box_map50_95": float(metrics.box.map),
            "seg_map50": float(metrics.seg.map50),
            "seg_map50_95": float(metrics.seg.map),
            **count_metrics,
        },
        "production_ready": False,
        "promotion_requirements": [
            "independent local field evaluation",
            "agronomist review and pilot approval",
            "license decision for inference runtime and weights",
        ],
    }
    report_path = run_dir / "baseline_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a short research-only YOLO segmentation baseline")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--weights", default="yolo11n-seg.pt")
    parser.add_argument("--name", default="apple_baseline")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.epochs < 1 or args.imgsz < 64 or args.batch < 1:
        print("FAIL training_parameters_invalid")
        return 1
    try:
        report = train(args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"FAIL {error}")
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
