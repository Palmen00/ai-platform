param(
    [switch]$Force
)

. (Join-Path $PSScriptRoot "..\lib\common.ps1")

if (-not $Force) {
    Write-Host "Refusing to remove Qdrant data without -Force."
    exit 1
}

Remove-DirectoryContents -Path (Join-RepoPath "data\qdrant")
Write-Host "Qdrant storage reset."
