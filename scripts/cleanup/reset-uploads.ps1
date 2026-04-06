param(
    [switch]$Force
)

. (Join-Path $PSScriptRoot "..\lib\common.ps1")

if (-not $Force) {
    Write-Host "Refusing to remove uploads without -Force."
    exit 1
}

Remove-DirectoryContents -Path (Join-RepoPath "data\uploads")
Write-Host "Upload storage reset."
