from src.export import _build_sheet_row


def test_build_sheet_row_matches_existing_sheet_columns():
    row = _build_sheet_row(
        {
            "ma_van_don": "141078299480",
            "don_vi_van_chuyen": "Viettel",
            "nguoi_gui": "Tung Bay",
            "sdt_gui": "1900 8095",
            "email_gui": "sender@example.com",
            "dia_chi_gui": "Sender address",
            "nguoi_nhan": "An Duang",
            "sdt_nhan": "1200 8095",
            "email_nhan": "receiver@example.com",
            "dia_chi_nhan": "TP. Thu Duc",
            "noi_dung_hang_hoa": "Thong bao Zalo",
            "tien_thu_ho": "55.000",
            "ngay_gio_gui": "05/05/2026 11:44:27",
            "trang_thai": "Pending",
            "need_review": "YES",
        }
    )

    assert row == [
        "141078299480",
        "Viettel",
        "Tung Bay",
        "1900 8095",
        "An Duang",
        "1200 8095",
        "TP. Thu Duc",
        "Thong bao Zalo",
        "55.000",
        "05/05/2026 11:44:27",
        "Pending",
    ]


def test_build_sheet_row_falls_back_to_receiver_email_and_pending_status():
    row = _build_sheet_row(
        {
            "ma_van_don": "A001",
            "email_nhan": "receiver@example.com",
        }
    )

    assert row[0] == "A001"
    assert row[5] == "receiver@example.com"
    assert row[10] == "Pending"
