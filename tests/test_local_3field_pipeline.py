import sys
from pathlib import Path

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
