param(
    [string]$Service = ""
)

. (Join-Path $PSScriptRoot "..\lib\common.ps1")

$arguments = @("logs", "-f")
if ($Service) {
    $arguments += $Service
}

Invoke-DockerCompose -Arguments $arguments
