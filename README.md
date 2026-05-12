# Mail Detection

Local-only mail form extraction for three regions:

- `sender`: sender block
- `receiver`: receiver block
- `barcode`: tracking number / barcode area

The runtime pipeline is:

```text
raw image
-> normalize / rotate / deskew
-> YOLOv8 detects sender, receiver, barcode
-> crop each region
-> OCR locally with EasyOCR or VietOCR
-> parse fields to JSON
-> optional Google Sheet append + email notification
```

## Sample

Detection preview:

![Sample detection](docs/assets/sample_detection.png)

Example output:

```json
{
  "ma_van_don": "90060964865",
  "nguoi_gui": "ACME VIETNAM CO., LTD",
  "sdt_gui": null,
  "dia_chi_gui": "12 Nguyen Hue, Q1, HCM",
  "nguoi_nhan": "CONG TY FES VIET NAM",
  "sdt_nhan": "0903058556",
  "dia_chi_nhan": "So 4, Duong so 8, VSIP 1",
  "trang_thai": "Pending",
  "need_review": "NO"
}
```

The sample image uses fake data. Real images and annotation data are intentionally not committed.

## Repository Contents

Important files:

```text
src/local_3field_pipeline.py      Main extraction CLI
src/detect_regions.py             YOLOv8 region detector wrapper
src/preprocessing.py              Image loading, HEIC support, rotate/deskew helpers
src/geometry.py                   Document orientation/perspective normalization
src/export.py                     Google Sheets + SMTP email export
src/auth_google.py                Google OAuth/service account auth
src/convert_roboflow_coco.py      Roboflow COCO -> YOLOv8 converter
models/yolo_regions/mail_3field/weights/best.pt
```

Data folders are ignored by git to keep the repository small.

## Environment Setup

Windows PowerShell:

```powershell
python -m venv .venv312
.\.venv312\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you already have `.venv312`, just activate it and install requirements.

## Google Sheets Setup

You can use either OAuth Desktop credentials or a Service Account.

### Option A: OAuth Desktop

1. Go to Google Cloud Console.
2. Create/select a project.
3. Enable these APIs:
   - Google Sheets API
   - Google Drive API
4. Configure OAuth consent screen.
5. Create OAuth Client ID:
   - Application type: Desktop app
6. Download the JSON file.
7. Save it in the repo root as `credentials.json`.
8. Run:

```powershell
.\.venv312\Scripts\python.exe setup_auth.py
```

This opens a browser and writes `token.json`.

### Option B: Service Account

1. Enable:
   - Google Sheets API
   - Google Drive API
2. Create a service account.
3. Create/download a service account key JSON.
4. Save it as `credentials.json`.
5. Share the target Google Sheet with the service account email.

No `setup_auth.py` run is needed for service accounts.

## Gmail / Email Setup

For Gmail SMTP:

1. Enable 2-Step Verification on the Gmail account.
2. Create an App Password:
   - Google Account -> Security -> App passwords
3. Use that app password as `SMTP_PASSWORD`.

SMTP settings:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_gmail_app_password
NOTIFY_EMAIL=recipient@gmail.com
```

## Environment Variables

Copy the example:

```powershell
Copy-Item .env.example .env
```

Fill:

```env
GOOGLE_SHEET_ID=your_google_sheet_id_here
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json

CONFIRM_BASE_URL=http://localhost:8080

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_gmail_app_password
NOTIFY_EMAIL=recipient@gmail.com
```

`CONFIRM_BASE_URL` is used to build the email "Confirm received" link.

## Run Extraction

Use the bundled model:

```powershell
.\.venv312\Scripts\python.exe -X utf8 .\src\local_3field_pipeline.py ".\path\to\image.jpg"
```

Use VietOCR backend:

```powershell
.\.venv312\Scripts\python.exe -X utf8 .\src\local_3field_pipeline.py ".\path\to\image.jpg" --ocr_backend vietocr
```

Save debug crops:

```powershell
.\.venv312\Scripts\python.exe -X utf8 .\src\local_3field_pipeline.py ".\path\to\image.jpg" --out_dir ".\debug_3field"
```

Export to Google Sheet and send email:

```powershell
.\.venv312\Scripts\python.exe -X utf8 .\src\local_3field_pipeline.py ".\path\to\image.jpg" --ocr_backend vietocr --export
```

Skip one export target:

```powershell
--export --no_email
--export --no_sheet
```

## Roboflow Dataset Conversion

Export Roboflow annotations as COCO, then convert:

```powershell
.\.venv312\Scripts\python.exe .\src\convert_roboflow_coco.py `
  --coco_dir "D:\path\to\roboflow_export.coco" `
  --out_dir ".\data\yolo_roboflow_3field"
```

This creates a YOLOv8 dataset with:

```text
barcode
receiver
sender
```

## Train YOLOv8

```powershell
.\.venv312\Scripts\yolo.exe task=detect mode=train `
  model=yolov8n.pt `
  data=data/yolo_roboflow_3field/data.yaml `
  epochs=80 imgsz=1024 batch=4 `
  project=models/yolo_regions name=mail_3field exist_ok=True
```

After training, copy the best weight to:

```text
models/yolo_regions/mail_3field/weights/best.pt
```

## Tests

```powershell
.\.venv312\Scripts\python.exe -m pytest tests -q
```

## Current Limitation

YOLO detection is strong enough for the current three-region task. The remaining quality bottleneck is OCR on handwritten Vietnamese fields. For production quality, collect reviewed line crops and fine-tune VietOCR or another local recognizer.
