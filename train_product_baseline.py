from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tarfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_dataset_root(root: Path) -> Path:
    candidates = [root, root / "SKU110K_fixed", *[path for path in root.glob("*") if path.is_dir()]]
    for candidate in candidates:
        if (candidate / "annotations" / "annotations_train.csv").exists():
            return candidate
    raise FileNotFoundError("SKU-110K annotations not found")


def convert_split(dataset_root: Path, split: str) -> int:
    annotations = dataset_root / "annotations" / f"annotations_{split}.csv"
    labels_dir = dataset_root / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[tuple[float, float, float, float, float, float]]] = {}
    with annotations.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            image, x1, y1, x2, y2, _class, width, height = row
            grouped.setdefault(image, []).append(tuple(map(float, (x1, y1, x2, y2, width, height))))
    with (dataset_root / f"{split}.txt").open("w", encoding="utf-8") as listing:
        for image_name, boxes in sorted(grouped.items()):
            listing.write(f"{(dataset_root / 'images' / image_name).resolve().as_posix()}\n")
            with (labels_dir / f"{Path(image_name).stem}.txt").open("w", encoding="utf-8") as labels:
                for x1, y1, x2, y2, width, height in boxes:
                    center_x = ((x1 + x2) / 2) / width
                    center_y = ((y1 + y2) / 2) / height
                    box_width = (x2 - x1) / width
                    box_height = (y2 - y1) / height
                    labels.write(f"0 {center_x:.6f} {center_y:.6f} {box_width:.6f} {box_height:.6f}\n")
    return len(grouped)


def prepare_dataset(archive: Path, output_root: Path) -> tuple[Path, dict[str, int]]:
    output_root.mkdir(parents=True, exist_ok=True)
    if not (output_root / "SKU110K_fixed").exists():
        with tarfile.open(archive, "r:gz") as handle:
            handle.extractall(output_root)
    dataset_root = find_dataset_root(output_root)
    counts = {split: convert_split(dataset_root, split) for split in ("train", "val", "test")}
    dataset_yaml = output_root / "dataset.yaml"
    dataset_yaml.write_text(
        f"path: {dataset_root.resolve().as_posix()}\ntrain: train.txt\nval: val.txt\ntest: test.txt\nnames:\n  0: product\n",
        encoding="utf-8",
    )
    return dataset_yaml, counts


def train(args: argparse.Namespace) -> Path:
    from ultralytics import YOLO

    dataset_yaml, counts = prepare_dataset(Path(args.archive), Path(args.data_root))
    model = YOLO(args.model)
    results = model.train(
        data=str(dataset_yaml), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device=args.device, workers=args.workers, project=str(Path(args.project)),
        name=args.name, exist_ok=True, patience=args.patience, cache=args.cache,
        pretrained=True, max_det=args.max_det,
    )
    best = Path(results.save_dir) / "weights" / "best.pt"
    report = {
        "status": "candidate",
        "task": "product_detection",
        "class_names": ["product"],
        "dataset": "SKU-110K",
        "dataset_license_scope": "research-only; do not use for commercial deployment without permission",
        "dataset_counts": counts,
        "archive_sha256": sha256_file(Path(args.archive)),
        "model_artifact": str(best),
        "model_artifact_sha256": sha256_file(best) if best.exists() else None,
        "training": vars(args),
        "metrics": {key: value for key, value in getattr(results, "results_dict", {}).items()},
    }
    report_path = Path(results.save_dir) / "product_baseline_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Treina um baseline de detecção genérica de produtos.")
    parser.add_argument("--archive", default="data/external/sku110k/SKU110K_fixed.tar.gz")
    parser.add_argument("--data-root", default="data/external/sku110k")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=-1)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--project", default="data/external/sku110k/runs")
    parser.add_argument("--name", default="product_baseline")
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--cache", default=False)
    parser.add_argument("--max-det", type=int, default=1000)
    args = parser.parse_args()
    print(f"[OK] product baseline report: {train(args)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
