param(
  [string]$Suite = "backend/evals/unstructured_structure_cases.json",
  [string]$WriteReport = ""
)

$scriptPath = Join-Path $PSScriptRoot "run_unstructured_structure_eval.py"
$arguments = @($scriptPath, "--suite", $Suite)

if ($WriteReport) {
  $arguments += @("--write-report", $WriteReport)
}

py -3 @arguments
