param(
    [string]$LogPath = "C:\LocalAIOS\logs",
    [int]$KeepDays = 14
)

$cutoff = (Get-Date).AddDays(-$KeepDays)
$deleted = 0

Get-ChildItem -Path $LogPath -Filter "*.log" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force
        $deleted += 1
    }

Write-Output "Deleted $deleted old log files from $LogPath"
