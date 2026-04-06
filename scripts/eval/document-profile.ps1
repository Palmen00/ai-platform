param(
  [string[]]$Documents,
  [string]$WriteReport = ""
)

$scriptPath = Join-Path $PSScriptRoot "prototype_document_profile.py"
$arguments = @($scriptPath)

if ($WriteReport) {
  $arguments += @("--write-report", $WriteReport)
}

if ($Documents -and $Documents.Count -gt 0) {
  $arguments += $Documents
}

py -3 @arguments
