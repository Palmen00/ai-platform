. (Join-Path $PSScriptRoot "..\lib\common.ps1")

Write-Host "Current infrastructure status:"
Invoke-DockerCompose -Arguments @("ps")
