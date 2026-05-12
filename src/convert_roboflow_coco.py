import argparse
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pillow_heif = None


DEFAULT_CLASS_MAP = {
    "barcode": "barcode",
    "receiver": "receiver",
    "sender": "sender",
}


def _safe_stem(name: str) -> str:
    return Path(name).stem.replace(" ", "_").replace("(", "").replace(")", "")


def _write_image(src: Path, dst: Path) -> None:
    if src.suffix.lower() == ".heic":
        img = Image.open(src).convert("RGB")
        img.save(dst.with_suffix(".jpg"), quality=95)
        return
    if dst.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        shutil.copy2(src, dst)
        return
    img = Image.open(src).convert("RGB")
    img.save(dst.with_suffix(".jpg"), quality=95)


def _yolo_bbox(coco_bbox: list[float], width: int, height: int) -> tuple[float, float, float, float]:
    x, y, w, h = [float(v) for v in coco_bbox]
    return (
        (x + w / 2.0) / width,
        (y + h / 2.0) / height,
        w / width,
        h / height,
    )


def convert(
    coco_dir: Path,
    out_dir: Path,
    train_ratio: float,
    val_ratio: float,
    seed: int,
) -> None:
    ann_path = coco_dir / "train" / "_annotations.coco.json"
    if not ann_path.exists():
        raise FileNotFoundError(f"COCO annotation not found: {ann_path}")

    data = json.loads(ann_path.read_text(encoding="utf-8"))
    categories = {int(c["id"]): c["name"] for c in data["categories"]}
    class_names = ["barcode", "receiver", "sender"]
    class_to_id = {name: idx for idx, name in enumerate(class_names)}

    images = {int(img["id"]): img for img in data["images"]}
    anns_by_image: dict[int, list[dict]] = defaultdict(list)
    skipped_categories: set[str] = set()
    for ann in data["annotations"]:
        cat_name = categories.get(int(ann["category_id"]), "")
        mapped = DEFAULT_CLASS_MAP.get(cat_name)
        if mapped is None:
            skipped_categories.add(cat_name)
            continue
        anns_by_image[int(ann["image_id"])].append({**ann, "_class": mapped})

    image_ids = [image_id for image_id in images if anns_by_image.get(image_id)]
    random.Random(seed).shuffle(image_ids)
    n_train = int(len(image_ids) * train_ratio)
    n_val = int(len(image_ids) * val_ratio)
    splits = {
        "train": image_ids[:n_train],
        "val": image_ids[n_train : n_train + n_val],
        "test": image_ids[n_train + n_val :],
    }

    for split in splits:
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    for split, ids in splits.items():
        for image_id in ids:
            img = images[image_id]
            src = coco_dir / "train" / img["file_name"]
            if not src.exists():
                raise FileNotFoundError(f"Image not found: {src}")

            stem = _safe_stem(img["file_name"])
            suffix = ".jpg" if src.suffix.lower() == ".heic" else src.suffix.lower()
            dst_img = out_dir / "images" / split / f"{stem}{suffix}"
            _write_image(src, dst_img)
            if src.suffix.lower() == ".heic":
                dst_img = dst_img.with_suffix(".jpg")

            lines = []
            for ann in anns_by_image[image_id]:
                cls_id = class_to_id[ann["_class"]]
                x, y, w, h = _yolo_bbox(ann["bbox"], int(img["width"]), int(img["height"]))
                lines.append(f"{cls_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
            (out_dir / "labels" / split / f"{dst_img.stem}.txt").write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )

    yaml_text = "\n".join(
        [
            f"path: {out_dir.as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "",
            f"nc: {len(class_names)}",
            "names:",
            *[f"  {i}: {name}" for i, name in enumerate(class_names)],
            "",
        ]
    )
    (out_dir / "data.yaml").write_text(yaml_text, encoding="utf-8")

    summary = {
        "images_total": len(image_ids),
        "annotations_total": sum(len(anns_by_image[i]) for i in image_ids),
        "splits": {split: len(ids) for split, ids in splits.items()},
        "classes": class_names,
        "skipped_categories": sorted(skipped_categories),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Roboflow COCO export to YOLOv8 3-field dataset.")
    parser.add_argument("--coco_dir", required=True)
    parser.add_argument("--out_dir", default="data/yolo_roboflow_3field")
    parser.add_argument("--train_ratio", type=float, default=0.8)
    parser.add_argument("--val_ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    convert(
        coco_dir=Path(args.coco_dir),
        out_dir=Path(args.out_dir),
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
