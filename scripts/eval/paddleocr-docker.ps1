param(
  [string]$Suite = "backend/evals/ocr_engine_cases.json",
  [string]$WriteReport = "temp/paddleocr-docker-report.json"
)

$repo = (Get-Location).Path
$containerCommand = @"
set -e
apt-get update >/dev/null
apt-get install -y libglib2.0-0 libgl1 libgomp1 >/dev/null
pip install --quiet paddleocr paddlepaddle pymupdf pillow >/tmp/paddle-pip.log 2>&1
export PYTHONIOENCODING=utf-8
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
export FLAGS_use_mkldnn=0
python /work/scripts/eval/prototype_paddleocr_compare.py --suite /work/$Suite --write-report /work/$WriteReport
"@

docker run --rm `
  -v "${repo}:/work" `
  -w /work `
  python:3.11-slim `
  bash -lc $containerCommand
