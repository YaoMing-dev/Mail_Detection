import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.detect_regions import detect_regions
    from src.export import push_to_sheet, send_notification_email
    from src.geometry import normalize_document
    from src.preprocessing import load_and_prepare
except ModuleNotFoundError:
    from detect_regions import detect_regions
    from export import push_to_sheet, send_notification_email
    from geometry import normalize_document
    from preprocessing import load_and_prepare


Box = Tuple[int, int, int, int, float]
_EASYOCR_READER = None
_VIETOCR_PREDICTOR = None
_PADDLEOCR_READER = None


if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIELDS = [
    "ma_van_don",
    "nguoi_gui",
    "sdt_gui",
    "dia_chi_gui",
    "nguoi_nhan",
    "sdt_nhan",
    "dia_chi_nhan",
]


def _best_box(boxes: List[Box]) -> Optional[Box]:
    if not boxes:
        return None
    return max(boxes, key=lambda b: b[4])


def _expand_box(box: Box, image_w: int, image_h: int, pad_ratio: float = 0.035) -> tuple[int, int, int, int]:
    x1, y1, x2, y2, _ = box
    pad = int(max(x2 - x1, y2 - y1) * pad_ratio)
    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(image_w, x2 + pad),
        min(image_h, y2 + pad),
    )


def _expand_tracking_box(box: Box, image_w: int, image_h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2, _ = box
    bw = x2 - x1
    bh = y2 - y1
    return (
        max(0, int(x1 - bw * 0.35)),
        max(0, int(y1 - bh * 0.35)),
        min(image_w, int(x2 + bw * 0.35)),
        min(image_h, int(y2 + bh * 0.45)),
    )


def _bw_for_ocr(crop_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, h=8, templateWindowSize=7, searchWindowSize=21)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        11,
    )


def _get_easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is not None:
        return _EASYOCR_READER
    import easyocr

    _EASYOCR_READER = easyocr.Reader(["vi", "en"], gpu=False, verbose=False)
    return _EASYOCR_READER


def _get_vietocr_predictor():
    global _VIETOCR_PREDICTOR
    if _VIETOCR_PREDICTOR is not None:
        return _VIETOCR_PREDICTOR
    import torch
    from vietocr.tool.config import Cfg
    from vietocr.tool.predictor import Predictor

    cfg = Cfg.load_config_from_name("vgg_transformer")
    cfg["device"] = "cuda" if torch.cuda.is_available() else "cpu"
    cfg["predictor"]["beamsearch"] = False
    _VIETOCR_PREDICTOR = Predictor(cfg)
    return _VIETOCR_PREDICTOR


def _get_paddleocr_reader():
    global _PADDLEOCR_READER
    if _PADDLEOCR_READER is not None:
        return _PADDLEOCR_READER
    from paddleocr import PaddleOCR
    import torch

    use_gpu = torch.cuda.is_available()
    _PADDLEOCR_READER = PaddleOCR(
        use_angle_cls=True,
        lang="vi",
        use_gpu=use_gpu,
        show_log=False,
    )
    print(f"[PaddleOCR] PP-OCRv4 vi, gpu={use_gpu}")
    return _PADDLEOCR_READER


def _ocr_crop(crop_bgr: np.ndarray, reader, min_conf: float = 0.25) -> Dict[str, object]:
    if crop_bgr.size == 0:
        return {"text": "", "lines": [], "confidence": 0.0}

    variants = [
        crop_bgr,
        cv2.cvtColor(_bw_for_ocr(crop_bgr), cv2.COLOR_GRAY2BGR),
    ]
    best = {"text": "", "lines": [], "confidence": 0.0}
    for variant in variants:
        raw = reader.readtext(variant, paragraph=False)
        accepted = [(str(text).strip(), float(conf)) for _, text, conf in raw if float(conf) >= min_conf and str(text).strip()]
        if not accepted:
            continue
        lines = [text for text, _ in accepted]
        confidence = sum(conf for _, conf in accepted) / len(accepted)
        text = "\n".join(lines)
        if len(text) > len(str(best["text"])) or confidence > float(best["confidence"]):
            best = {"text": text, "lines": lines, "confidence": confidence}
    return best


def _ocr_crop_vietocr(crop_bgr: np.ndarray, detector, recognizer, min_det_conf: float = 0.12) -> Dict[str, object]:
    if crop_bgr.size == 0:
        return {"text": "", "lines": [], "confidence": 0.0}
    from PIL import Image

    raw = detector.readtext(crop_bgr, paragraph=False)
    h, w = crop_bgr.shape[:2]
    items = []
    for points, easy_text, conf in raw:
        if float(conf) < min_det_conf:
            continue
        xs = [int(p[0]) for p in points]
        ys = [int(p[1]) for p in points]
        x1 = max(0, min(xs) - 8)
        y1 = max(0, min(ys) - 8)
        x2 = min(w, max(xs) + 8)
        y2 = min(h, max(ys) + 8)
        line_crop = crop_bgr[y1:y2, x1:x2]
        if line_crop.size == 0:
            continue
        pil = Image.fromarray(cv2.cvtColor(line_crop, cv2.COLOR_BGR2RGB))
        text = _normalize_text(str(recognizer.predict(pil)))
        if not text:
            text = _normalize_text(str(easy_text))
        items.append((y1, x1, text, float(conf)))

    items.sort(key=lambda item: (item[0], item[1]))
    lines = [text for _, _, text, _ in items if text]
    confidence = sum(conf for *_, conf in items) / len(items) if items else 0.0
    return {"text": "\n".join(lines), "lines": lines, "confidence": confidence}


def _ocr_crop_paddle_vietocr(
    crop_bgr: np.ndarray,
    paddle_reader,
    vietocr_recognizer,
) -> Dict[str, object]:
    """Detect text boxes with PaddleOCR, then recognize each box with VietOCR."""
    if crop_bgr.size == 0:
        return {"text": "", "lines": [], "confidence": 0.0}
    from PIL import Image

    try:
        det_result = paddle_reader.ocr(crop_bgr, rec=False, cls=False)
    except Exception as exc:
        print(f"[PaddleOCR] detection error: {exc}")
        return {"text": "", "lines": [], "confidence": 0.0}

    if not det_result or not det_result[0]:
        return {"text": "", "lines": [], "confidence": 0.0}

    h, w = crop_bgr.shape[:2]
    items = []
    for box_pts in det_result[0]:
        try:
            xs = [int(p[0]) for p in box_pts]
            ys = [int(p[1]) for p in box_pts]
        except (TypeError, IndexError):
            continue
        x1 = max(0, min(xs) - 4)
        y1 = max(0, min(ys) - 4)
        x2 = min(w, max(xs) + 4)
        y2 = min(h, max(ys) + 4)
        line_crop = crop_bgr[y1:y2, x1:x2]
        if line_crop.size == 0:
            continue
        pil = Image.fromarray(cv2.cvtColor(line_crop, cv2.COLOR_BGR2RGB))
        try:
            text = _normalize_text(str(vietocr_recognizer.predict(pil)))
        except Exception:
            text = ""
        if not text:
            continue
        items.append((y1, x1, text))

    items.sort(key=lambda it: (it[0], it[1]))
    lines = [text for _, _, text in items]
    confidence = 0.85 if lines else 0.0
    return {
        "text": "\n".join(lines),
        "lines": lines,
        "confidence": confidence,
    }


def _decode_barcode(crop_bgr: np.ndarray) -> Optional[str]:
    if not hasattr(cv2, "barcode_BarcodeDetector") or crop_bgr.size == 0:
        return None
    detector = cv2.barcode_BarcodeDetector()
    for img in (crop_bgr, cv2.cvtColor(_bw_for_ocr(crop_bgr), cv2.COLOR_GRAY2BGR)):
        try:
            decoded, _, _ = detector.detectAndDecode(img)
        except cv2.error:
            continue
        decoded = str(decoded).strip()
        if decoded:
            return decoded
    return None


def _normalize_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def _fold_text(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _extract_phone(text: str) -> Optional[str]:
    pools = [_normalize_text(line) for line in text.splitlines() if _normalize_text(line)]
    for pool in pools:
        compact = re.sub(r"[^\d]", "", pool)
        for match in re.finditer(r"0\d{9,10}", compact):
            value = match.group(0)
            if not value.startswith(("1800", "1900")):
                return value
    return None


def _looks_like_label(line: str) -> bool:
    low = line.lower()
    folded = _fold_text(line)
    compact = re.sub(r"[^a-z0-9]+", "", folded)
    if line.strip().endswith(":") and len(line.strip()) <= 24:
        return True
    return any(
        token in low or token in folded
        for token in (
            "người",
            "nguoi",
            "gui",
            "nhan",
            "noi dung",
            "dung",
            "người gửi",
            "nguoi gui",
            "người nhận",
            "nguoi nhan",
            "nội dung",
            "noi dung",
            "ward",
            "province",
            "post code",
            "điện thoại",
            "dien thoai",
            "tel",
            "ten",
            "dia chi",
            "sender",
            "receiver",
            "recipient",
            "tracking",
            "phone number",
            "postal code",
            "weight",
            "sender s name",
            "sender s address",
            "recipient s name",
            "recipient s address",
            "ems",
            "chuyen phat",
            "hotline",
            "website",
        )
    ) or compact in {
        "ten",
        "diachi",
        "nguoigui",
        "nguoinhan",
        "mabuuchinh",
        "dienthoai",
        "phonenumber",
        "sendersname",
        "sendersaddress",
        "recipientsname",
        "recipientsaddress",
        "postalcode",
        "trackingnumber",
    } or ("dung" in folded and len(line) < 20)


def _extract_tracking(text: str) -> Optional[str]:
    candidates = []
    for line in text.splitlines():
        folded = _fold_text(line)
        if any(token in folded for token in ("sender", "recipient", "address", "phone", "weight", "postal", "nguoi", "dia chi", "dien thoai")):
            continue
        compact = re.sub(r"[^A-Za-z0-9]", "", line).upper()
        if not compact:
            continue
        candidates.extend(re.findall(r"\d{8,15}", compact))
        candidates.extend(re.findall(r"[A-Z]{2}\d{8,13}[A-Z]{0,3}", compact))
    candidates = [c for c in candidates if not c.startswith(("1800", "1900"))]
    if not candidates:
        return None
    return max(candidates, key=len)


def _clean_lines(lines: List[str]) -> List[str]:
    cleaned = []
    for line in lines:
        line = _normalize_text(line)
        if not line:
            continue
        folded = _fold_text(line)
        if folded in {"vicinam", "sinon"}:
            continue
        if _looks_like_label(line):
            right = line.split(":", 1)[-1].strip() if ":" in line else ""
            if right and not _looks_like_label(right):
                cleaned.append(right)
            continue
        cleaned.append(line)
    return cleaned


def _slice_sender_lines(lines: List[str]) -> List[str]:
    out = []
    for line in lines:
        folded = _fold_text(line)
        if "dung" in folded or "noi dung" in folded:
            break
        ascii_line = line.lower().encode("ascii", "ignore").decode("ascii")
        if "dung" in ascii_line or "nội dung" in line.lower() or "noi dung" in line.lower():
            break
        out.append(line)
    return out


def _slice_receiver_lines(lines: List[str]) -> List[str]:
    marker_idx = None
    for i, line in enumerate(lines):
        if "nhan" in _fold_text(line):
            marker_idx = i
            break
    if marker_idx is None:
        return lines

    content_idx = None
    for i, line in enumerate(lines[:marker_idx]):
        folded = _fold_text(line)
        if "noi dung" in folded or "dung" in folded:
            content_idx = i
            break

    before_marker = []
    if content_idx is not None:
        before_marker = lines[content_idx + 1 : marker_idx]
        before_marker = [
            line for line in before_marker
            if not re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", line)
            and not re.search(r"\bt\d\b", _fold_text(line))
        ]
    return before_marker + lines[marker_idx + 1 :]


def _parse_party(lines: List[str], role: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if role == "sender":
        lines = _slice_sender_lines(lines)
    elif role == "receiver":
        lines = _slice_receiver_lines(lines)
    lines = _clean_lines(lines)
    blob = "\n".join(lines)
    phone = _extract_phone(blob)
    if phone is None:
        loose_digits = [
            re.sub(r"[^\d]", "", line)
            for line in lines
            if 8 <= len(re.sub(r"[^\d]", "", line)) <= 11
        ]
        for value in loose_digits:
            if value.startswith("0") and not value.startswith(("1800", "1900")):
                phone = value
                break
    non_phone_lines = []
    for line in lines:
        digits = re.sub(r"[^\d]", "", line)
        if _extract_phone(line) or (phone and digits == phone):
            continue
        non_phone_lines.append(line)

    name_parts = []
    address_parts = []
    for line in non_phone_lines:
        folded = _fold_text(line)
        starts_address = bool(
            re.search(r"\d", line)
            or any(token in folded for token in ("duong", "phuong", "quan", "huyen", "tinh", "thanh pho", "ward", "province", "hcm", "vsip"))
        )
        if not address_parts and not starts_address and len(line) >= 2 and not _looks_like_label(line):
            name_parts.append(line)
            continue
        if not _looks_like_label(line):
            address_parts.append(line)

    name = _normalize_text(" ".join(name_parts)) or None
    address = _normalize_text(" ".join(address_parts)) or None
    return name, phone, address


def parse_fields(ocr: Dict[str, Dict[str, object]]) -> Dict[str, Optional[str]]:
    sender_name, sender_phone, sender_addr = _parse_party(list(ocr.get("sender_block", {}).get("lines", [])), "sender")
    receiver_name, receiver_phone, receiver_addr = _parse_party(list(ocr.get("receiver_block", {}).get("lines", [])), "receiver")
    tracking_text = str(ocr.get("tracking_number", {}).get("text", ""))
    tracking = ocr.get("tracking_number", {}).get("barcode") or _extract_tracking(tracking_text)
    return {
        "ma_van_don": tracking,
        "don_vi_van_chuyen": None,
        "nguoi_gui": sender_name,
        "sdt_gui": sender_phone,
        "email_gui": None,
        "dia_chi_gui": sender_addr,
        "nguoi_nhan": receiver_name,
        "sdt_nhan": receiver_phone,
        "email_nhan": None,
        "dia_chi_nhan": receiver_addr,
        "noi_dung_hang_hoa": None,
        "tien_thu_ho": None,
        "ngay_gio_gui": None,
        "trang_thai": "Pending",
    }


def _export_result(fields: Dict[str, Optional[str]], *, send_sheet: bool, send_email: bool) -> None:
    if send_sheet:
        push_to_sheet(
            fields,
            sheet_id=os.environ["GOOGLE_SHEET_ID"],
            credentials_file=os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
            token_file=os.environ.get("GOOGLE_TOKEN_FILE", "token.json"),
        )
    if send_email:
        send_notification_email(
            data=fields,
            confirm_base_url=os.environ["CONFIRM_BASE_URL"],
            smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ["SMTP_USER"],
            smtp_password=os.environ["SMTP_PASSWORD"],
            notify_email=os.environ["NOTIFY_EMAIL"],
        )


def process_image(
    image_path: str,
    model_path: str,
    out_dir: str = "debug_3field",
    save_debug: bool = True,
    ocr_backend: str = "paddleocr",
) -> Dict[str, object]:
    src = Path(image_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    img_rgb = load_and_prepare(src)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    img_bgr, geom = normalize_document(img_bgr)
    h, w = img_bgr.shape[:2]

    regions = detect_regions(img_bgr, model_path=model_path)
    if save_debug:
        preview = img_bgr.copy()
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
            box = _best_box(boxes)
            if not box:
                continue
            x1, y1, x2, y2, conf = box
            color = colors.get(cls_name, (255, 255, 255))
            cv2.rectangle(preview, (x1, y1), (x2, y2), color, 3)
            cv2.putText(
                preview,
                f"{labels.get(cls_name, cls_name)} {conf:.2f}",
                (x1, max(24, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
                cv2.LINE_AA,
            )
        cv2.imwrite(str(out / f"{src.stem}_preview.jpg"), preview)
    easyocr_reader = _get_easyocr_reader()
    paddle_reader = _get_paddleocr_reader() if ocr_backend == "paddleocr" else None
    recognizer = _get_vietocr_predictor() if ocr_backend in ("vietocr", "paddleocr") else None
    ocr: Dict[str, Dict[str, object]] = {}
    crops_meta = {}

    for cls_name in ("sender_block", "receiver_block", "tracking_number"):
        box = _best_box(regions.get(cls_name, []))
        if not box:
            ocr[cls_name] = {"text": "", "lines": [], "confidence": 0.0}
            crops_meta[cls_name] = None
            continue
        if cls_name == "tracking_number":
            x1, y1, x2, y2 = _expand_tracking_box(box, w, h)
        else:
            x1, y1, x2, y2 = _expand_box(box, w, h)
        crop = img_bgr[y1:y2, x1:x2]
        crops_meta[cls_name] = {"box": [x1, y1, x2, y2], "confidence": box[4]}
        if save_debug:
            cv2.imwrite(str(out / f"{src.stem}_{cls_name}.jpg"), crop)
            cv2.imwrite(str(out / f"{src.stem}_{cls_name}_bw.jpg"), _bw_for_ocr(crop))
        if cls_name == "tracking_number":
            ocr[cls_name] = _ocr_crop(crop, easyocr_reader)
        elif ocr_backend == "paddleocr":
            ocr[cls_name] = _ocr_crop_paddle_vietocr(crop, paddle_reader, recognizer)
        elif ocr_backend == "vietocr":
            ocr[cls_name] = _ocr_crop_vietocr(crop, easyocr_reader, recognizer)
        else:
            ocr[cls_name] = _ocr_crop(crop, easyocr_reader)
        if cls_name == "tracking_number":
            barcode_value = _decode_barcode(crop)
            if barcode_value:
                ocr[cls_name]["barcode"] = barcode_value
                if not ocr[cls_name]["text"]:
                    ocr[cls_name]["text"] = barcode_value
                    ocr[cls_name]["lines"] = [barcode_value]

    fields = parse_fields(ocr)
    valid_sender_phone = bool(re.fullmatch(r"0\d{9,10}", str(fields.get("sdt_gui") or "")))
    valid_receiver_phone = bool(re.fullmatch(r"0\d{9,10}", str(fields.get("sdt_nhan") or "")))
    need_review = (
        any(not fields.get(field) for field in ("ma_van_don", "nguoi_gui", "nguoi_nhan"))
        or not valid_sender_phone
        or not valid_receiver_phone
    )
    fields["need_review"] = "YES" if need_review else "NO"
    result = {
        "source_image": str(src),
        "geometry": geom,
        "crops": crops_meta,
        "ocr": ocr,
        "fields": fields,
        "need_review": need_review,
    }
    if save_debug:
        (out / f"{src.stem}_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Local 3-field mail extraction: YOLO crop -> local OCR -> JSON.")
    parser.add_argument("image")
    parser.add_argument(
        "--model",
        default="models/yolo_regions/mail_3field/weights/best.pt",
    )
    parser.add_argument("--out_dir", default="debug_3field")
    parser.add_argument("--no_debug", action="store_true")
    parser.add_argument("--ocr_backend", choices=["paddleocr", "vietocr", "easyocr"], default="paddleocr")
    parser.add_argument("--export", action="store_true", help="Append result to Google Sheet and send email.")
    parser.add_argument("--no_sheet", action="store_true", help="When --export is set, skip Google Sheet append.")
    parser.add_argument("--no_email", action="store_true", help="When --export is set, skip notification email.")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    result = process_image(
        args.image,
        args.model,
        out_dir=args.out_dir,
        save_debug=not args.no_debug,
        ocr_backend=args.ocr_backend,
    )
    if args.export:
        _export_result(
            result["fields"],
            send_sheet=not args.no_sheet,
            send_email=not args.no_email,
        )
    print(json.dumps(result["fields"], ensure_ascii=False, indent=2))
    print(f"need_review={result['need_review']}")


if __name__ == "__main__":
    main()
