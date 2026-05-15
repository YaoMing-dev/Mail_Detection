# install.ps1 - Setup mail-ocr-ner (Python 3.14 + Pillow 12 compatible)
# Run: .\install.ps1

Write-Host "=== Step 1: Base packages ===" -ForegroundColor Cyan
pip install torch transformers tokenizers pillow pillow-heif opencv-python numpy datasets seqeval gspread google-auth

Write-Host "`n=== Step 2: vietocr (no-deps to avoid Pillow conflict) ===" -ForegroundColor Cyan
pip install vietocr --no-deps

Write-Host "`n=== Step 3: vietocr deps (skip albumentations+imgaug, need C++ compiler) ===" -ForegroundColor Cyan
pip install "einops==0.2.0" "lmdb>=1.0.0" "prefetch-generator==1.0.1" "gdown>=4.4.0"

Write-Host "`n=== Step 4: Patch vietocr (remove imgaug/albumentations imports) ===" -ForegroundColor Cyan
python patch_vietocr.py

Write-Host "`n=== Step 5: Verify imports ===" -ForegroundColor Cyan
python check_imports.py

Write-Host "`n=== Step 6: PaddleOCR (GPU) ===" -ForegroundColor Cyan
pip install paddlepaddle-gpu paddleocr
Write-Host "  PaddleOCR models se duoc download tu dong khi chay lan dau" -ForegroundColor Yellow

Write-Host "`nDone! Next step:" -ForegroundColor Green
Write-Host "  python src/preprocessing.py"
