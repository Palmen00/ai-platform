param(
  [string]$Suite = "backend/evals/ocr_engine_cases.json",
  [string]$WriteReport = ""
)

$scriptPath = Join-Path $PSScriptRoot "prototype_easyocr_compare.py"
$arguments = @($scriptPath, "--suite", $Suite)

if ($WriteReport) {
  $arguments += @("--write-report", $WriteReport)
}

py -3 -X utf8 @arguments
