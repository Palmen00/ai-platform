. (Join-Path $PSScriptRoot "..\lib\common.ps1")

& (Join-Path $PSScriptRoot "..\setup\ensure-directories.ps1")

Write-Host "Starting infrastructure services..."
Invoke-DockerCompose -Arguments @("up", "-d")
Ensure-QdrantRunning
