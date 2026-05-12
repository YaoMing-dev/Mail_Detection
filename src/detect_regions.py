# src/detect_regions.py
from typing import Dict, List, Tuple

import numpy as np

# (x1, y1, x2, y2, confidence)
Box = Tuple[int, int, int, int, float]

CLASS_ALIASES = {
    "sender": "sender_block",
    "receiver": "receiver_block",
    "barcode": "tracking_number",
}


def _is_plausible_box(cls_name: str, x1: int, y1: int, x2: int, y2: int, image_w: int, image_h: int) -> bool:
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)
    area_ratio = (bw * bh) / max(1, image_w * image_h)
    if bw < 20 or bh < 20:
        return False

    if cls_name == "tracking_number":
        return 0.003 <= area_ratio <= 0.20
    if cls_name in {"sender_block", "receiver_block"}:
        return 0.003 <= area_ratio <= 0.60
    return 0.002 <= area_ratio <= 0.55


def _pick_best_sender_box(boxes: List[Box], image_w: int, image_h: int) -> List[Box]:
    """Keep only one sender box with a layout-aware score."""
    if not boxes:
        return []

    image_area = max(1, image_w * image_h)
    scored: List[Tuple[float, bool, Box]] = []
    for box in boxes:
        x1, y1, x2, y2, conf = box
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        area_ratio = (bw * bh) / image_area
        cx_ratio = ((x1 + x2) / 2.0) / max(1, image_w)
        cy_ratio = ((y1 + y2) / 2.0) / max(1, image_h)

        # Sender block is usually moderate-size and left-biased on these forms.
        size_penalty = max(0.0, area_ratio - 0.20) * 1.8
        right_penalty = max(0.0, cx_ratio - 0.55) * 0.8
        low_penalty = max(0.0, cy_ratio - 0.70) * 0.3
        score = conf - size_penalty - right_penalty - low_penalty

        valid_shape = 0.01 <= area_ratio <= 0.45
        scored.append((score, valid_shape, box))

    candidates = [item for item in scored if item[1]] or scored
    best = max(candidates, key=lambda item: item[0])[2]
    return [best]


def detect_regions(
    image: np.ndarray,
    model_path: str = "runs/detect/models/yolo_regions/phieu_gui_v1/weights/best.pt",
    conf_threshold: float = 0.18,
    sender_conf_threshold: float = 0.30,
    nms_iou: float = 0.50,
    keep_single_sender: bool = True,
    imgsz: int = 1024,
) -> Dict[str, List[Box]]:
    import ultralytics  # noqa: PLC0415 — lazy import keeps patch("ultralytics.YOLO") effective
    model = ultralytics.YOLO(model_path)
    regions: Dict[str, List[Box]] = {}
    h, w = image.shape[:2]

    def _collect(conf: float, iou: float, sender_conf: float) -> Dict[str, List[Box]]:
        out: Dict[str, List[Box]] = {}
        results = model(image, conf=conf, iou=iou, imgsz=imgsz, verbose=False)
        for result in results:
            for box in result.boxes:
                raw_cls_name = result.names[int(box.cls.item())]
                cls_name = CLASS_ALIASES.get(raw_cls_name, raw_cls_name)
                score = float(box.conf.item())
                if cls_name == "sender_block" and score < sender_conf:
                    continue
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                if not _is_plausible_box(cls_name, x1, y1, x2, y2, image_w=w, image_h=h):
                    continue
                out.setdefault(cls_name, []).append((x1, y1, x2, y2, score))
        return out

    regions = _collect(conf_threshold, nms_iou, sender_conf_threshold)
    if not regions:
        # Fallback for hard images (rotation/glare): relax thresholds once.
        regions = _collect(conf=0.18, iou=0.50, sender_conf=0.35)

    if keep_single_sender and regions.get("sender_block"):
        regions["sender_block"] = _pick_best_sender_box(regions["sender_block"], image_w=w, image_h=h)

    return regions


def train_yolo(
    data_yaml: str = "data/yolo_dataset/data.yaml",
    base_model: str = "yolov8n.pt",
    epochs: int = 100,
    imgsz: int = 1024,
    batch: int = 8,
    project: str = "models/yolo_regions",
    name: str = "phieu_gui_v1",
) -> str:
    import ultralytics  # noqa: PLC0415
    model = ultralytics.YOLO(base_model)
    model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project=project,
        name=name,
        exist_ok=True,
    )
    best_path = f"runs/detect/{project}/{name}/weights/best.pt"
    print(f"Training done. Best weights: {best_path}")
    return best_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")

    train_p = subparsers.add_parser("train", help="Fine-tune YOLOv8 trên dataset phiếu")
    train_p.add_argument("--data", default="data/yolo_dataset/data.yaml")
    train_p.add_argument("--epochs", type=int, default=100)
    train_p.add_argument("--batch", type=int, default=8)
    train_p.add_argument("--imgsz", type=int, default=1024)

    args = parser.parse_args()
    if args.cmd == "train":
        train_yolo(data_yaml=args.data, epochs=args.epochs, batch=args.batch, imgsz=args.imgsz)
    else:
        parser.print_help()
