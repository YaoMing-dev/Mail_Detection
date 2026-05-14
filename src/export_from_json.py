import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_3field_pipeline import _export_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Export existing extracted fields to Google Sheet and/or email.")
    parser.add_argument("json_file")
    parser.add_argument("--no_sheet", action="store_true")
    parser.add_argument("--no_email", action="store_true")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    fields = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    _export_result(fields, send_sheet=not args.no_sheet, send_email=not args.no_email)
    print(json.dumps({"ok": True, "sheet": not args.no_sheet, "email": not args.no_email}, ensure_ascii=False))


if __name__ == "__main__":
    main()
