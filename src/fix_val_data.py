"""
Clean train_corrected.txt and val_corrected.txt before VietOCR retraining.

Removes rows with empty labels, malformed rows, or labels that contain no
alphanumeric characters.

Run:
  python src/fix_val_data.py
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LABEL_DIR = ROOT / "data" / "ocr_labels"


def is_valid_label(label: str) -> bool:
    stripped = label.strip()
    if not stripped:
        return False
    return any(ch.isalnum() for ch in stripped)


def clean_file(path: Path) -> tuple[int, int]:
    if not path.exists():
        print(f"  SKIP (not found): {path}")
        return 0, 0

    lines = path.read_text(encoding="utf-8").splitlines()
    kept = []
    removed = 0
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("\t", 1)
        if len(parts) != 2:
            removed += 1
            continue
        img_path, label = parts[0], parts[1]
        if not is_valid_label(label):
            print(f"  REMOVE bad label [{label!r}] <- {img_path}")
            removed += 1
            continue
        kept.append(raw)

    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return len(kept), removed


def main() -> None:
    for fname in ("train_corrected.txt", "val_corrected.txt"):
        path = LABEL_DIR / fname
        print(f"\n=== {fname} ===")
        kept, removed = clean_file(path)
        print(f"  kept: {kept}  |  removed: {removed}")
    print("\nDone. Retrain with:")
    print("  python src/train_vietocr.py")


if __name__ == "__main__":
    main()
