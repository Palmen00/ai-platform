param(
  [string]$Suite = "backend/evals/document_profile_cases.json",
  [string]$WriteReport = ""
)

$scriptPath = Join-Path $PSScriptRoot "run_document_profile_eval.py"
$arguments = @($scriptPath, "--suite", $Suite)

if ($WriteReport) {
  $arguments += @("--write-report", $WriteReport)
}

py -3 @arguments
