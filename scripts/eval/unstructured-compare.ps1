param(
  [string[]]$Documents
)

$scriptPath = Join-Path $PSScriptRoot "prototype_unstructured_compare.py"

if ($Documents -and $Documents.Count -gt 0) {
  py -3 $scriptPath @Documents
} else {
  py -3 $scriptPath
}
