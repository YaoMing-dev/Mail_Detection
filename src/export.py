import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from typing import Dict, List, Optional

import gspread

from src.auth_google import get_gspread_client

# Existing Google Sheet layout, columns A -> K.
SHEET_COLUMNS_A_TO_K: List[str] = [
    "ma_van_don",
    "don_vi_van_chuyen",
    "nguoi_gui",
    "sdt_gui",
    "nguoi_nhan",
    "sdt_nhan",
    "dia_chi_nhan",
    "noi_dung_hang_hoa",
    "tien_thu_ho",
    "ngay_gio_gui",
    "trang_thai",
]
DEFAULT_EXPORT_WORKSHEET = "Mail OCR Export"


def _first_value(data: Dict[str, Optional[str]], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _build_sheet_row(data: Dict[str, Optional[str]]) -> List[str]:
    row = [
        _first_value(data, "ma_van_don"),
        _first_value(data, "don_vi_van_chuyen"),
        _first_value(data, "nguoi_gui"),
        _first_value(data, "sdt_gui"),
        _first_value(data, "nguoi_nhan"),
        _first_value(data, "sdt_nhan", "email_nhan"),
        _first_value(data, "dia_chi_nhan"),
        _first_value(data, "noi_dung_hang_hoa"),
        _first_value(data, "tien_thu_ho"),
        _first_value(data, "ngay_gio_gui"),
        _first_value(data, "trang_thai") or "Pending",
    ]
    if not row[9]:
        row[9] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return row


def _get_or_create_export_worksheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    title = os.environ.get("GOOGLE_SHEET_WORKSHEET", DEFAULT_EXPORT_WORKSHEET).strip() or DEFAULT_EXPORT_WORKSHEET
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(SHEET_COLUMNS_A_TO_K))

    header = worksheet.row_values(1)[: len(SHEET_COLUMNS_A_TO_K)]
    if header != SHEET_COLUMNS_A_TO_K:
        worksheet.update(range_name="A1:K1", values=[SHEET_COLUMNS_A_TO_K], value_input_option="RAW")
        worksheet.freeze(rows=1)
    return worksheet


def _next_export_row(worksheet: gspread.Worksheet) -> int:
    values_in_column_a = worksheet.col_values(1)
    return max(2, len(values_in_column_a) + 1)


def push_to_sheet(
    data: Dict[str, Optional[str]],
    sheet_id: str,
    credentials_file: str = "credentials.json",
    token_file: str = "token.json",
) -> None:
    gc = get_gspread_client(credentials_file=credentials_file, token_file=token_file)
    ws = _get_or_create_export_worksheet(gc.open_by_key(sheet_id))
    row = _build_sheet_row(data)
    target_row = _next_export_row(ws)
    ws.update(range_name=f"A{target_row}:K{target_row}", values=[row], value_input_option="USER_ENTERED")


def _build_html(data: Dict[str, Optional[str]], confirm_url: str) -> str:
    def v(key: str) -> str:
        return str(data.get(key) or "")

    return f"""<!doctype html>
<html>
<body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222">
  <h2>Mail OCR - New shipment</h2>
  <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
    <tr><td><b>Tracking</b></td><td>{v("ma_van_don")}</td></tr>
    <tr><td><b>Carrier</b></td><td>{v("don_vi_van_chuyen")}</td></tr>
    <tr><td><b>Sender</b></td><td>{v("nguoi_gui")} - {v("sdt_gui")}</td></tr>
    <tr><td><b>Sender address</b></td><td>{v("dia_chi_gui")}</td></tr>
    <tr><td><b>Receiver</b></td><td>{v("nguoi_nhan")} - {v("sdt_nhan")}</td></tr>
    <tr><td><b>Receiver address</b></td><td>{v("dia_chi_nhan")}</td></tr>
    <tr><td><b>Needs review</b></td><td>{v("need_review")}</td></tr>
  </table>
  <p>
    <a href="{confirm_url}"
       style="background:#2e7d32;color:white;padding:12px 20px;text-decoration:none;border-radius:4px;display:inline-block">
      Confirm received
    </a>
  </p>
</body>
</html>"""


def send_notification_email(
    data: Dict[str, Optional[str]],
    confirm_base_url: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    notify_email: str,
) -> None:
    ma_van_don = data.get("ma_van_don") or ""
    confirm_url = f"{confirm_base_url.rstrip('/')}/api/confirm-received?id={ma_van_don}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Mail OCR] Tracking {ma_van_don}"
    msg["From"] = smtp_user
    msg["To"] = notify_email
    msg.attach(MIMEText(_build_html(data, confirm_url), "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
