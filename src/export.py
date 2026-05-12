import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

from src.auth_google import get_gspread_client

SHEET_COLUMNS: List[str] = [
    "ma_van_don",
    "don_vi_van_chuyen",
    "nguoi_gui",
    "sdt_gui",
    "email_gui",
    "dia_chi_gui",
    "nguoi_nhan",
    "sdt_nhan",
    "email_nhan",
    "dia_chi_nhan",
    "noi_dung_hang_hoa",
    "tien_thu_ho",
    "ngay_gio_gui",
    "trang_thai",
    "need_review",
    "ngay_nhan",
]


def push_to_sheet(
    data: Dict[str, Optional[str]],
    sheet_id: str,
    credentials_file: str = "credentials.json",
    token_file: str = "token.json",
) -> None:
    gc = get_gspread_client(credentials_file=credentials_file, token_file=token_file)
    ws = gc.open_by_key(sheet_id).sheet1
    row = [data.get(col) or "" for col in SHEET_COLUMNS[:-1]]
    row.append("")
    ws.append_row(row)


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
