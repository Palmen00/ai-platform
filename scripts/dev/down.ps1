. (Join-Path $PSScriptRoot "..\lib\common.ps1")

Write-Host "Stopping infrastructure services..."
Invoke-DockerCompose -Arguments @("down")
