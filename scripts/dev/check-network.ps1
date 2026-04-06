param(
    [int]$Top = 12
)

$ErrorActionPreference = "Stop"

function Get-ProcessLabel {
    param([int]$ProcessId)

    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        return "$($process.ProcessName) ($ProcessId)"
    } catch {
        return "unknown ($ProcessId)"
    }
}

function Get-ExternalConnections {
    Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue |
        Where-Object {
            $_.RemoteAddress -notin @("127.0.0.1", "::1", "0.0.0.0") -and
            $_.LocalAddress -notin @("127.0.0.1", "::1", "0.0.0.0")
        }
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

$topProcesses = Get-Process |
    Sort-Object CPU -Descending |
    Select-Object -First $Top ProcessName, Id, CPU, @{Name="WorkingSetMB";Expression={[math]::Round($_.WS / 1MB, 1)}}

$externalConnections = Get-ExternalConnections

$connectionSummary = $externalConnections |
    Group-Object OwningProcess |
    Sort-Object Count -Descending |
    Select-Object -First $Top @{Name="Process";Expression={Get-ProcessLabel -ProcessId ([int]$_.Name)}}, Count

$aiRelated = Get-Process |
    Where-Object {
        $_.ProcessName -match "python|node|ollama|qdrant|docker"
    } |
    Select-Object ProcessName, Id, CPU, @{Name="WorkingSetMB";Expression={[math]::Round($_.WS / 1MB, 1)}}, Path

$aiExternal = $externalConnections |
    Where-Object { $_.OwningProcess -in ($aiRelated.Id) } |
    Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, OwningProcess,
        @{Name="Process";Expression={Get-ProcessLabel -ProcessId $_.OwningProcess}}

Write-Host "Network hotspot check for Local AI OS" -ForegroundColor Green
Write-Host ("Timestamp: {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

Write-Section "Top CPU Processes"
$topProcesses | Format-Table -AutoSize

Write-Section "Top External Connection Counts"
if ($connectionSummary) {
    $connectionSummary | Format-Table -AutoSize
} else {
    Write-Host "No established external TCP connections found."
}

Write-Section "AI Stack Processes"
if ($aiRelated) {
    $aiRelated | Format-Table -AutoSize
} else {
    Write-Host "No AI-related processes found."
}

Write-Section "AI Stack External Connections"
if ($aiExternal) {
    $aiExternal | Format-Table -AutoSize
} else {
    Write-Host "No external connections found for python/node/ollama/qdrant/docker processes."
}

Write-Section "Active Network Adapters"
Get-NetAdapterStatistics |
    Select-Object Name, @{Name="ReceivedMB";Expression={[math]::Round($_.ReceivedBytes / 1MB, 2)}}, @{Name="SentMB";Expression={[math]::Round($_.SentBytes / 1MB, 2)}} |
    Sort-Object ReceivedMB -Descending |
    Format-Table -AutoSize

