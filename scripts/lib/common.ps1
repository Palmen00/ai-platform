Set-StrictMode -Version Latest

function Get-RepoRoot {
    return Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

function Join-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    return Join-Path (Get-RepoRoot) $RelativePath
}

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Ensure-ProjectDirectories {
    $directories = @(
        (Join-RepoPath "data\app"),
        (Join-RepoPath "data\app\cache"),
        (Join-RepoPath "data\qdrant"),
        (Join-RepoPath "data\uploads"),
        (Join-RepoPath "logs"),
        (Join-RepoPath "logs\backend"),
        (Join-RepoPath "temp")
    )

    foreach ($directory in $directories) {
        Ensure-Directory -Path $directory
    }
}

function Remove-DirectoryContents {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -Path $Path)) {
        return
    }

    Get-ChildItem -Path $Path -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

function Remove-PathIfPresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -Path $Path) {
        Remove-Item -Path $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-DockerCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $infraPath = Join-RepoPath "infra"

    Push-Location $infraPath
    try {
        & docker compose @Arguments
    }
    finally {
        Pop-Location
    }
}

function Test-QdrantHealthy {
    param(
        [string[]]$Urls = @(
            "http://127.0.0.1:6333/healthz",
            "http://127.0.0.1:6333/collections"
        ),
        [int]$TimeoutSeconds = 3
    )

    foreach ($url in $Urls) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec $TimeoutSeconds
            if (-not $response.Content) {
                continue
            }

            $payload = $response.Content | ConvertFrom-Json
            if ($payload.status -eq "ok") {
                return $true
            }
        }
        catch {
            continue
        }
    }

    return $false
}

function Ensure-QdrantRunning {
    param(
        [int]$TimeoutSeconds = 45
    )

    if (Test-QdrantHealthy) {
        Write-Host "Qdrant is already healthy." -ForegroundColor Green
        return
    }

    Write-Host "Qdrant is not reachable. Ensuring container is running..." -ForegroundColor Yellow
    try {
        Invoke-DockerCompose -Arguments @("up", "-d", "qdrant")
    }
    catch {
        throw "Could not start Qdrant through Docker. Make sure Docker Desktop is running, then try again."
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-QdrantHealthy) {
            Write-Host "Qdrant is healthy." -ForegroundColor Green
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "Qdrant did not become healthy within $TimeoutSeconds seconds."
}
