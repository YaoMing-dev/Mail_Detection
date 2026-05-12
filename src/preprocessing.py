"""
preprocessing.py — Stage 1: GPU-accelerated preprocessing (memory-safe)
------------------------------------------------------------------------
Chay:
  python src/preprocessing.py
  python src/preprocessing.py --workers 4
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

DEFAULT_INPUT  = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "processed"


# ── I/O (CPU, Unicode-safe) ───────────────────────────────────────────────────

def load_pil(path: Path) -> Image.Image:
    if path.suffix.upper() == ".HEIC":
        import pillow_heif
        pillow_heif.register_heif_opener()
    return Image.open(path).convert("RGB")


def save_png(arr: np.ndarray, dst: Path):
    _, buf = cv2.imencode(".png", arr)
    dst.write_bytes(buf.tobytes())


# ── CPU: load + resize + deskew (chay parallel duoc) ─────────────────────────

def auto_rotate_90(img_rgb: np.ndarray) -> np.ndarray:
    """Nếu ảnh bị xoay 90°/270° (portrait chụp ngang), tự rotate lại.
    Dùng text orientation detection qua projection profile."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    h, w = binary.shape
    # Nếu ảnh cao hơn rộng nhiều mà text chạy ngang → cần rotate
    # Kiểm tra bằng horizontal vs vertical projection variance
    h_proj = binary.sum(axis=1).astype(float)  # sum theo hàng → text tạo peaks
    v_proj = binary.sum(axis=0).astype(float)  # sum theo cột

    h_var = float(np.var(h_proj))
    v_var = float(np.var(v_proj))

    # Nếu variance dọc >> ngang trong ảnh portrait → text đang chạy theo chiều dọc → rotate
    if h < w:
        return img_rgb  # ảnh ngang rồi, không cần rotate
    if v_var > h_var * 2.0:
        # Text chạy dọc → rotate 90° ngược chiều kim đồng hồ
        return np.rot90(img_rgb, k=1).copy()
    return img_rgb


def load_and_prepare(path: Path) -> np.ndarray:
    """Load HEIC/PNG, auto-rotate 90° nếu cần, deskew. Tra ve RGB uint8."""
    pil = load_pil(path)
    img = np.array(pil)
    img = auto_rotate_90(img)
    img = deskew_cpu(img)
    return img


def deskew_cpu(img_rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 150)
    if lines is None:
        return img_rgb
    angles = []
    for rho, theta in lines[:, 0]:
        angle = (theta - np.pi / 2) * 180 / np.pi
        if abs(angle) < 20:
            angles.append(angle)
    if not angles:
        return img_rgb
    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return img_rgb
    h, w = img_rgb.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
    return cv2.warpAffine(img_rgb, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


# ── GPU: grayscale + denoise + CLAHE + threshold (SEQUENTIAL, 1 anh 1 luc) ───

def preprocess_gpu(img_rgb: np.ndarray, device: torch.device) -> np.ndarray:
    import kornia

    with torch.no_grad():
        # fp16 de giam VRAM ~50% so voi fp32, du chinh xac cho anh nhi phan
        t = (torch.from_numpy(img_rgb)
             .permute(2, 0, 1).unsqueeze(0)
             .half().to(device)) / 255.0          # (1, 3, H, W) float16

        # Grayscale → (1, 1, H, W)
        gray = kornia.color.rgb_to_grayscale(t)

        # Denoise: Gaussian separable — O(H*W*k) khong phai O(H*W*k^2)
        gray = kornia.filters.gaussian_blur2d(
            gray.float(), (5, 5), (1.5, 1.5)      # CLAHE can float32
        )

        # CLAHE
        gray = kornia.enhance.equalize_clahe(gray, clip_limit=2.0, grid_size=(8, 8))

        # Otsu: tinh tren CPU — retval la gia tri threshold, dst la anh (bo qua)
        gray_np = (gray.squeeze().cpu().numpy() * 255).astype(np.uint8)
        t_val, _ = cv2.threshold(gray_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        t_val = t_val / 255.0

        binary = (gray.squeeze() > t_val).to(torch.uint8) * 255
        result = binary.cpu().numpy()

    del t, gray, binary
    torch.cuda.empty_cache()
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir",  default=str(DEFAULT_INPUT))
    p.add_argument("--output_dir", default=str(DEFAULT_OUTPUT))
    p.add_argument("--workers", type=int, default=4,
                   help="So thread load anh song song (default: 4)")
    args = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU   : {torch.cuda.get_device_name(0)}")
        # Cho phep allocator dung segment linh hoat hon
        import os
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    src_dir = Path(args.input_dir)
    dst_dir = Path(args.output_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    exts = {".jpg", ".jpeg", ".png", ".heic"}
    images = sorted(f for f in src_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in exts)

    if not images:
        print(f"Khong co anh nao trong {src_dir}")
        return

    print(f"Xu ly {len(images)} anh (load parallel x{args.workers}, GPU sequential)...")
    t0 = time.time()

    # Buoc 1: Load + resize + deskew SONG SONG tren CPU
    print("  [1/2] Loading & deskewing (CPU parallel)...")
    prepared: dict[str, np.ndarray | Exception] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(load_and_prepare, src): src for src in images}
        for fut, src in future_map.items():
            try:
                prepared[src.name] = fut.result()
            except Exception as e:
                prepared[src.name] = e
                print(f"    FAIL load {src.name}: {e}")

    # Buoc 2: GPU processing TUAN TU (1 anh 1 luc, tranh OOM)
    print("  [2/2] GPU processing (sequential)...")
    ok, fail = 0, 0
    for src in images:
        dst = dst_dir / (src.stem + ".png")
        data = prepared.get(src.name)
        if isinstance(data, Exception):
            fail += 1
            continue
        try:
            binary = preprocess_gpu(data, device)
            save_png(binary, dst)
            print(f"    OK {src.name}")
            ok += 1
        except Exception as e:
            print(f"    FAIL {src.name}: {e}")
            torch.cuda.empty_cache()
            fail += 1

    elapsed = time.time() - t0
    print(f"\nXong: {ok} thanh cong, {fail} loi — {elapsed:.1f}s")
    print(f"Anh da xu ly: {dst_dir.resolve()}")


if __name__ == "__main__":
    main()
