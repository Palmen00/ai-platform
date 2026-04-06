param(
    [switch]$Reload,
    [switch]$LowImpact = $true,
    [ValidateSet("Idle", "BelowNormal", "Normal", "AboveNormal", "High")]
    [string]$Priority = "BelowNormal"
)

$ErrorActionPreference = "Stop"

$commonScript = Join-Path $PSScriptRoot "..\lib\common.ps1"
. $commonScript

Ensure-QdrantRunning

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"

$envAssignments = @()
if ($LowImpact) {
    $envAssignments += '$env:LOW_IMPACT_MODE="true"'
    if (-not $env:OLLAMA_EMBED_BATCH_SIZE) {
        $envAssignments += '$env:OLLAMA_EMBED_BATCH_SIZE="8"'
    }
}

$uvicornArgs = @("-m", "uvicorn", "main:app")
if ($Reload) {
    $uvicornArgs += "--reload"
}

$uvicornCommand = "py -3 " + ($uvicornArgs -join " ")
$commandParts = @("Set-Location '$backendDir'")
if ($envAssignments.Count -gt 0) {
    $commandParts += $envAssignments
}
$commandParts += $uvicornCommand
$command = $commandParts -join "; "

$process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @("-NoExit", "-Command", $command) `
    -WorkingDirectory $backendDir `
    -PassThru

Start-Sleep -Milliseconds 300
try {
    $process.PriorityClass = $Priority
} catch {
    Write-Warning "Could not set backend process priority to $Priority."
}

Write-Host "Started backend in a separate PowerShell window." -ForegroundColor Green
Write-Host "PID: $($process.Id)"
Write-Host "Priority: $Priority"
Write-Host "Low impact mode: $LowImpact"
Write-Host "Reload enabled: $Reload"
