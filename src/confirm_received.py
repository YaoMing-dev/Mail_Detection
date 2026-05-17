import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth_google import get_gspread_client
from src.export import DEFAULT_EXPORT_WORKSHEET


def confirm_received(ma_van_don: str) -> dict:
    if not ma_van_don.strip():
        raise ValueError("Missing ma_van_don")

    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        raise RuntimeError("Missing GOOGLE_SHEET_ID")

    worksheet_title = os.environ.get("GOOGLE_SHEET_WORKSHEET", DEFAULT_EXPORT_WORKSHEET).strip() or DEFAULT_EXPORT_WORKSHEET
    gc = get_gspread_client(
        credentials_file=os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        token_file=os.environ.get("GOOGLE_TOKEN_FILE", "token.json"),
    )
    worksheet = gc.open_by_key(sheet_id).worksheet(worksheet_title)

    values = worksheet.col_values(1)
    row_number = next(
        (
            index
            for index, value in reversed(list(enumerate(values, start=1)))
            if index > 1 and value.strip() == ma_van_don.strip()
        ),
        None,
    )
    if row_number is None:
        raise LookupError(f"ma_van_don {ma_van_don!r} not found in worksheet {worksheet_title!r}")
    if row_number == 1:
        raise LookupError("ma_van_don matched header row, not a shipment row")

    worksheet.update_cell(row_number, 11, "Received")
    return {
        "ok": True,
        "ma_van_don": ma_van_don,
        "worksheet": worksheet_title,
        "row": row_number,
        "status": "Received",
        "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark a shipment as received in Google Sheet.")
    parser.add_argument("ma_van_don")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    print(json.dumps(confirm_received(args.ma_van_don), ensure_ascii=False))


if __name__ == "__main__":
    main()
