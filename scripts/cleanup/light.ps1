. (Join-Path $PSScriptRoot "..\lib\common.ps1")

& (Join-Path $PSScriptRoot "..\setup\ensure-directories.ps1")

Write-Host "Running light cleanup..."

docker container prune -f
docker image prune -f
docker builder prune -f

Remove-DirectoryContents -Path (Join-RepoPath "temp")
Remove-DirectoryContents -Path (Join-RepoPath "data\app\cache")
Remove-PathIfPresent -Path (Join-RepoPath "frontend\.next")
Remove-PathIfPresent -Path (Join-RepoPath "backend\__pycache__")

Write-Host "Light cleanup completed."
