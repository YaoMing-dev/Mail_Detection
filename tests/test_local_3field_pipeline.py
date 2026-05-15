import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_parse_fields_filters_labels_and_maps_parties():
    from src.local_3field_pipeline import parse_fields

    ocr = {
        "sender_block": {
            "lines": [
                "NGƯỜI GỬI:",
                "JP VIETNAM CO., LTD",
                "Lầu 8, 666/10/3 Đường 3/2, Q.10, HCM",
                "Tel: 02839975045",
                "NỘI DUNG",
            ],
            "text": "",
        },
        "receiver_block": {
            "lines": [
                "NỘI DUNG",
                "Bảng kê 7/4/2026",
                "NGƯỜI NHẬN:",
                "Công ty TNHH FES (Việt Nam)",
                "Số 4, đường số 8, VSIP 1",
                "Số điện thoại (Tel)",
            ],
            "text": "",
        },
        "tracking_number": {
            "lines": ["30009684695"],
            "text": "30009684695",
        },
    }

    result = parse_fields(ocr)

    assert result["ma_van_don"] == "30009684695"
    assert result["nguoi_gui"] == "JP VIETNAM CO., LTD"
    assert result["sdt_gui"] == "02839975045"
    assert result["dia_chi_gui"] == "Lầu 8, 666/10/3 Đường 3/2, Q.10, HCM"
    assert result["nguoi_nhan"] == "Công ty TNHH FES (Việt Nam)"
    assert result["dia_chi_nhan"] == "Số 4, đường số 8, VSIP 1"


def test_parse_fields_prefers_decoded_barcode():
    from src.local_3field_pipeline import parse_fields

    result = parse_fields(
        {
            "sender_block": {"lines": [], "text": ""},
            "receiver_block": {"lines": [], "text": ""},
            "tracking_number": {
                "lines": ["bad OCR 123"],
                "text": "bad OCR 123",
                "barcode": "90060964865",
            },
        }
    )

    assert result["ma_van_don"] == "90060964865"


def test_ocr_crop_paddle_vietocr_empty_image():
    import numpy as np
    from unittest.mock import MagicMock
    from src.local_3field_pipeline import _ocr_crop_paddle_vietocr

    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    result = _ocr_crop_paddle_vietocr(empty, MagicMock(), MagicMock())
    assert result == {"text": "", "lines": [], "confidence": 0.0}


def test_ocr_crop_paddle_vietocr_no_detection():
    import numpy as np
    from unittest.mock import MagicMock
    from src.local_3field_pipeline import _ocr_crop_paddle_vietocr

    paddle_mock = MagicMock()
    paddle_mock.ocr.return_value = [[]]
    crop = np.zeros((100, 300, 3), dtype=np.uint8)
    result = _ocr_crop_paddle_vietocr(crop, paddle_mock, MagicMock())
    assert result["text"] == ""
    assert result["lines"] == []


def test_ocr_crop_paddle_vietocr_with_boxes():
    import numpy as np
    from unittest.mock import MagicMock
    from src.local_3field_pipeline import _ocr_crop_paddle_vietocr

    crop = np.ones((200, 400, 3), dtype=np.uint8) * 255
    paddle_mock = MagicMock()
    paddle_mock.ocr.return_value = [
        [
            [[10, 50], [200, 50], [200, 80], [10, 80]],
            [[10, 10], [200, 10], [200, 40], [10, 40]],
        ]
    ]

    vietocr_mock = MagicMock()
    vietocr_mock.predict.side_effect = ["Nguyen Van A", "0912345678"]

    result = _ocr_crop_paddle_vietocr(crop, paddle_mock, vietocr_mock)
    assert result["lines"] == ["0912345678", "Nguyen Van A"]
    assert "0912345678" in result["text"]


def test_parse_fields_rejects_ocr_garbage_as_name():
    from src.local_3field_pipeline import parse_fields

    ocr = {
        "sender_block": {
            "lines": [
                "NGUOI GUI",
                "Ten:",
                "Sender's name",
                "Minh Gia",
                "Dia chi:",
                "Sender's address",
                "0937580738",
            ],
            "text": "",
        },
        "receiver_block": {
            "lines": [
                "NGUOI NHAN",
                "Ten:",
                "Recipient's name",
                "Curf",
                "Nam)",
                "Dia chi:",
                "Recipient's address",
                "Klw",
                "Jinge",
                "0331769433",
            ],
            "text": "",
        },
        "tracking_number": {"lines": ["30009684695"], "text": "30009684695"},
    }

    result = parse_fields(ocr)
    nguoi_nhan = result.get("nguoi_nhan") or ""
    assert "Nam)" not in nguoi_nhan
    assert "Klw" not in nguoi_nhan
    assert result["sdt_gui"] == "0937580738"
    assert result["sdt_nhan"] == "0331769433"


def test_ocr_crop_prefers_confidence_over_length():
    from src.local_3field_pipeline import _ocr_crop
    from unittest.mock import MagicMock
    import numpy as np

    reader_mock = MagicMock()
    reader_mock.readtext.side_effect = [
        [(None, "Nguyen Van A", 0.95)],
        [(None, "Nguyen Van AXXXXXXXXXXXXXXXXXXXXXXXXX", 0.30)],
    ]
    crop = np.zeros((50, 200, 3), dtype=np.uint8)
    result = _ocr_crop(crop, reader_mock, min_conf=0.25)
    assert result["text"] == "Nguyen Van A"
    assert result["confidence"] == pytest.approx(0.95, rel=0.01)


def test_extract_phone_9_digit_fallback():
    from src.local_3field_pipeline import _extract_phone

    assert _extract_phone("Dien thoai: 093758073") == "093758073"
    assert _extract_phone("0937580738\n093758073") == "0937580738"
    assert _extract_phone("12345678") is None
