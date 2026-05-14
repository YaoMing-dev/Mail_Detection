import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.detect_regions import detect_regions
from src.geometry import normalize_document
from src.preprocessing import load_and_prepare


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a JPG detection preview without OCR.")
    parser.add_argument("image")
    parser.add_argument("--model", default="models/yolo_regions/mail_3field/weights/best.pt")
    parser.add_argument("--out_dir", default="debug_3field")
    args = parser.parse_args()

    src = Path(args.image)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    img_rgb = load_and_prepare(src)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    img_bgr, _ = normalize_document(img_bgr)
    regions = detect_regions(img_bgr, model_path=args.model)

    colors = {
        "sender_block": (255, 120, 40),
        "receiver_block": (40, 220, 120),
        "tracking_number": (40, 160, 255),
    }
    labels = {
        "sender_block": "SENDER",
        "receiver_block": "RECEIVER",
        "tracking_number": "TRACKING",
    }

    for cls_name, boxes in regions.items():
        if not boxes:
            continue
        x1, y1, x2, y2, conf = max(boxes, key=lambda b: b[4])
        color = colors.get(cls_name, (255, 255, 255))
        cv2.rectangle(img_bgr, (x1, y1), (x2, y2), color, 3)
        cv2.putText(
            img_bgr,
            f"{labels.get(cls_name, cls_name)} {conf:.2f}",
            (x1, max(24, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
            cv2.LINE_AA,
        )

    preview_path = out / f"{src.stem}_preview.jpg"
    cv2.imwrite(str(preview_path), img_bgr)
    print(preview_path)


if __name__ == "__main__":
    main()
