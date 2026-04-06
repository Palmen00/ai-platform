param(
  [string]$Suite = "backend/evals/docling_structure_cases.json",
  [string]$WriteReport = ""
)

$scriptPath = Join-Path $PSScriptRoot "run_docling_compare_eval.py"
$arguments = @($scriptPath, "--suite", $Suite)

if ($WriteReport) {
  $arguments += @("--write-report", $WriteReport)
}

py -3 @arguments
