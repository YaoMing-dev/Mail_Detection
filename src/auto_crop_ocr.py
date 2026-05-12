"""
auto_crop_ocr.py — Tự động crop từng dòng chữ từ ảnh đã preprocess
---------------------------------------------------------------------
Chạy:
  python src/auto_crop_ocr.py
  python src/auto_crop_ocr.py --val_ratio 0.2 --no_ocr

Mặc định đọc từ data/processed (output của preprocessing.py).
Kết quả: data/ocr_crops/ và data/ocr_labels/train.txt + val.txt
→ Mở 2 file txt, sửa label sai → train VietOCR.
"""

import argparse
import os
import random
import shutil
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent.parent


def detect_lines(img_gray: np.ndarray,
                 kw: int = 40, kh: int = 3) -> list[tuple[int, int, int, int]]:
    """Trả về list (x, y, w, h) của từng dòng chữ theo thứ tự từ trên xuống."""
    h_img, w_img = img_gray.shape[:2]

    # Loại noise nhỏ trước khi dilate (opening = erosion + dilation)
    noise_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    inv = cv2.bitwise_not(img_gray)
    inv = cv2.morphologyEx(inv, cv2.MORPH_OPEN, noise_k)

    # Dilate ngang để gộp ký tự thành dòng
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kw, kh))
    dilated = cv2.dilate(inv, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Ngưỡng scale theo độ phân giải ảnh
    # Dòng chữ thật: cao ít nhất 0.5% chiều cao, rộng ít nhất 5% chiều rộng
    # và phải có aspect ratio w/h > 1.5 (ngang hơn dọc)
    min_h = max(15, h_img // 200)
    min_w = max(80, w_img // 20)

    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if h < min_h or h > h_img * 0.4:
            continue
        if w < min_w:
            continue
        if w / h < 1.5:
            continue
        # Pixel density: dòng chữ thật có ít nhất 3% pixel đen trong bounding box
        # Noise blob thưa thớt có density < 1%
        region = img_gray[y:y+h, x:x+w]
        dark_pixels = np.sum(region < 128)
        density = dark_pixels / (w * h)
        if density < 0.03:
            continue
        pad = max(4, h_img // 500)
        x = max(0, x - pad)
        y = max(0, y - pad)
        w = min(w_img - x, w + pad * 2)
        h = min(h_img - y, h + pad * 2)
        boxes.append((x, y, w, h))

    boxes.sort(key=lambda b: b[1])
    return boxes


def detect_lines_with_fallback(img_gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Thử nhiều kernel width + nếu vẫn thất bại, thử adaptive threshold
    (xử lý được ảnh nền màu như nền đỏ sau khi binarize thành đen)."""
    # Thử kernel thường trước
    for kw in [40, 60, 80, 20]:
        boxes = detect_lines(img_gray, kw=kw, kh=3)
        if boxes:
            return boxes

    # Fallback: dùng adaptive threshold thay Otsu — tốt hơn với ảnh nền không đều
    adaptive = cv2.adaptiveThreshold(
        img_gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )
    for kw in [40, 60, 80]:
        boxes = detect_lines(adaptive, kw=kw, kh=3)
        if boxes:
            return boxes

    return []


def run_vietocr_base(img_paths: list[Path]) -> dict[str, str]:
    """Chạy VietOCR pretrained base model, trả về {img_path_str: predicted_text}."""
    try:
        from vietocr.tool.predictor import Predictor
        from vietocr.tool.config import Cfg
        from PIL import Image
    except ImportError:
        print("[Warning] vietocr chua cai — label se de trong")
        return {str(p): "" for p in img_paths}

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  VietOCR device: {device}")

    cfg = Cfg.load_config_from_name("vgg_transformer")
    cfg["device"] = device
    # Khong set cfg['weights'] → Predictor tu dong download pretrained weights
    predictor = Predictor(cfg)

    results = {}
    total = len(img_paths)
    for i, p in enumerate(img_paths, 1):
        try:
            img = Image.open(p).convert("RGB")
            text = predictor.predict(img)
            results[str(p)] = text
        except Exception as e:
            results[str(p)] = ""
            print(f"  [OCR error] {p.name}: {e}")
        if i % 100 == 0 or i == total:
            print(f"  OCR: {i}/{total}")
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", default="data/processed",
                   help="Thư mục ảnh đã preprocess")
    p.add_argument("--crop_dir", default="data/ocr_crops",
                   help="Output thư mục crop")
    p.add_argument("--label_dir", default="data/ocr_labels",
                   help="Output thư mục label txt")
    p.add_argument("--val_ratio", type=float, default=0.2)
    p.add_argument("--no_ocr", action="store_true",
                   help="Bỏ qua bước chạy VietOCR base (label để trống)")
    args = p.parse_args()

    src_dir = Path(args.input_dir)
    crop_dir = Path(args.crop_dir)
    label_dir = Path(args.label_dir)

    # Xoa crop cu de khong bi lan file tu run truoc
    import shutil
    for split in ["train", "val"]:
        split_dir = crop_dir / split
        if split_dir.exists():
            shutil.rmtree(split_dir)
        split_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(src_dir.glob("*.png"))
    if not images:
        print(f"Không có ảnh PNG nào trong {src_dir}")
        return

    random.seed(42)
    random.shuffle(images)
    n_val = max(1, int(len(images) * args.val_ratio))
    val_set = set(str(p) for p in images[:n_val])

    all_crops: dict[str, list[Path]] = {"train": [], "val": []}
    total_crops = 0

    print(f"Crop dòng từ {len(images)} ảnh...")
    for img_path in images:
        split = "val" if str(img_path) in val_set else "train"
        # Dung Pillow tranh loi Unicode path tren Windows
        try:
            from PIL import Image as PILImage
            img = np.array(PILImage.open(img_path).convert("L"))
        except Exception as e:
            print(f"  ✗ Khong doc duoc: {img_path.name}: {e}")
            continue

        boxes = detect_lines_with_fallback(img)
        if not boxes:
            print(f"  ✗ Không detect được dòng: {img_path.name}")
            continue

        for i, (x, y, w, h) in enumerate(boxes):
            crop = img[y:y+h, x:x+w]
            crop_name = f"{img_path.stem}_line{i:03d}.png"
            crop_path = crop_dir / split / crop_name
            # Unicode-safe: encode sang bytes roi write
            _, buf = cv2.imencode(".png", crop)
            crop_path.write_bytes(buf.tobytes())
            all_crops[split].append(crop_path)
            total_crops += 1

        print(f"  ✓ {img_path.name}: {len(boxes)} dòng → {split}/")

    print(f"\nTổng crops: {total_crops} ({len(all_crops['train'])} train / {len(all_crops['val'])} val)")

    for split, crop_paths in all_crops.items():
        label_file = label_dir / f"{split}.txt"
        if args.no_ocr:
            ocr_results = {str(p): "" for p in crop_paths}
        else:
            print(f"\nChạy VietOCR base trên {len(crop_paths)} crops ({split})...")
            ocr_results = run_vietocr_base(crop_paths)

        with open(label_file, "w", encoding="utf-8") as f:
            for cp in crop_paths:
                text = ocr_results.get(str(cp), "")
                # Dùng path tương đối từ ROOT
                rel = cp.resolve().relative_to(ROOT.resolve())
                f.write(f"{rel}\t{text}\n")

        print(f"Label file: {label_file} ({len(crop_paths)} dòng)")

    print(f"""
=== BƯỚC TIẾP THEO ===
1. Mở file data/ocr_labels/train.txt và val.txt
2. Sửa những label sai (VietOCR base có thể nhận sai ~20-30%)
3. Xóa các dòng crop rác (border, logo, v.v.)
4. Khi xong → chạy train VietOCR:
   python src/train_vietocr.py
""")


if __name__ == "__main__":
    main()
