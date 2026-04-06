param(
  [string]$Suite = "backend/evals/ocr_engine_cases.json",
  [string]$WriteReport = "temp/ocrmypdf-docker-report.json"
)

$repo = (Get-Location).Path
$containerCommand = @"
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update >/dev/null
apt-get install -y --no-install-recommends ghostscript qpdf tesseract-ocr tesseract-ocr-eng tesseract-ocr-swe pngquant >/dev/null
pip install --quiet --no-cache-dir pymupdf ocrmypdf >/tmp/ocrmypdf-pip.log 2>&1
export PYTHONIOENCODING=utf-8
python /work/scripts/eval/prototype_ocrmypdf_compare.py --suite /work/$Suite --write-report /work/$WriteReport
"@

docker run --rm `
  -v "${repo}:/work" `
  -w /work `
  python:3.11-slim `
  bash -lc $containerCommand
