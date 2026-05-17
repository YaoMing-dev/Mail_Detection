import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth_google import get_gspread_client
from src.export import DEFAULT_EXPORT_WORKSHEET


def worksheet_url(sheet_id: str, worksheet_title: str) -> str:
    spreadsheet = get_gspread_client(
        credentials_file=os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        token_file=os.environ.get("GOOGLE_TOKEN_FILE", "token.json"),
    ).open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(worksheet_title)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={worksheet.id}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the Google Sheets URL for the configured export worksheet.")
    parser.add_argument("sheet_id")
    parser.add_argument("--worksheet", default=os.environ.get("GOOGLE_SHEET_WORKSHEET", DEFAULT_EXPORT_WORKSHEET))
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    print(json.dumps({"url": worksheet_url(args.sheet_id, args.worksheet)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
