# Spring Boot API

API wrapper for the existing Python OCR pipeline.

## Requirements

- JDK 17+
- Maven 3.9+
- MongoDB, when you want persistence
- Existing Python environment from the repo root

## Run

From `backend-spring`:

```powershell
$env:MONGODB_URI="mongodb://localhost:27017/mail_ocr"
mvn spring-boot:run
```

Useful overrides:

```powershell
$env:MAIL_OCR_PROJECT_ROOT="D:\Dev\Nghĩa\mail-ocr-ner"
$env:MAIL_OCR_PYTHON="D:\Dev\Nghĩa\mail-ocr-ner\.venv312\Scripts\python.exe"
$env:MAIL_OCR_BACKEND="easyocr"
```

Endpoints:

- `POST /api/shipments/extract` multipart field `file`, optional `ocrBackend=easyocr|vietocr`
- `GET /api/shipments`
- `GET /api/shipments/review`
- `PUT /api/shipments/{id}/review`
