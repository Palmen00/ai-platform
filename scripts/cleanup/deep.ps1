. (Join-Path $PSScriptRoot "..\lib\common.ps1")

& (Join-Path $PSScriptRoot "..\setup\ensure-directories.ps1")

Write-Host "Running deep cleanup..."

docker system prune -a -f

Remove-DirectoryContents -Path (Join-RepoPath "temp")
Remove-DirectoryContents -Path (Join-RepoPath "data\app\cache")
Remove-DirectoryContents -Path (Join-RepoPath "logs\backend")
Remove-PathIfPresent -Path (Join-RepoPath "frontend\.next")
Remove-PathIfPresent -Path (Join-RepoPath "frontend\node_modules\.cache")
Remove-PathIfPresent -Path (Join-RepoPath "backend\__pycache__")

Write-Host "Deep cleanup completed."
Write-Host "User uploads and Qdrant data were preserved."
