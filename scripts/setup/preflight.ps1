param(
    [switch]$Json
)

. (Join-Path $PSScriptRoot "..\lib\common.ps1")

Set-StrictMode -Version Latest

function New-CheckResult {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [ValidateSet("ok", "warning", "error")]
        [string]$Status,
        [Parameter(Mandatory = $true)]
        [string]$Detail,
        [string]$Hint = ""
    )

    return [pscustomobject]@{
        name = $Name
        status = $Status
        detail = $Detail
        hint = $Hint
    }
}

function Get-CommandVersion {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    try {
        $output = & $Command[0] $Command[1..($Command.Length - 1)] 2>$null
        return (($output | Select-Object -First 1) -as [string]).Trim()
    }
    catch {
        return ""
    }
}

function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        return [pscustomobject]@{
            ok = $true
            statusCode = [int]$response.StatusCode
            detail = "reachable"
        }
    }
    catch {
        $statusCode = 0
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }

        return [pscustomobject]@{
            ok = $false
            statusCode = $statusCode
            detail = $_.Exception.Message
        }
    }
}

function Get-RuntimeUrls {
    $defaults = @{
        ollama_base_url = "http://127.0.0.1:11434"
        qdrant_url = "http://127.0.0.1:6333"
    }

    $settingsPath = Join-RepoPath "data\app\settings.json"
    if (-not (Test-Path $settingsPath)) {
        return $defaults
    }

    try {
        $runtime = Get-Content $settingsPath -Raw | ConvertFrom-Json
        if ($runtime.ollama_base_url) {
            $defaults.ollama_base_url = [string]$runtime.ollama_base_url
        }
        if ($runtime.qdrant_url) {
            $defaults.qdrant_url = [string]$runtime.qdrant_url
        }
    }
    catch {
    }

    return $defaults
}

function Add-CommandCheck {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Name,
        [string]$Executable,
        [string[]]$VersionCommand,
        [string]$MissingHint
    )

    $command = Get-Command $Executable -ErrorAction SilentlyContinue
    if (-not $command) {
        $Results.Add((New-CheckResult -Name $Name -Status "error" -Detail "not found" -Hint $MissingHint))
        return
    }

    $version = ""
    if ($VersionCommand.Count -gt 0) {
        $version = Get-CommandVersion -Command $VersionCommand
    }

    $detail = if ($version) { $version } else { $command.Source }
    $Results.Add((New-CheckResult -Name $Name -Status "ok" -Detail $detail))
}

$results = [System.Collections.Generic.List[object]]::new()
Ensure-ProjectDirectories

Add-CommandCheck -Results $results -Name "python" -Executable "py" -VersionCommand @("py", "-3", "--version") -MissingHint "Install Python 3.13 and make sure `py` works."
Add-CommandCheck -Results $results -Name "node" -Executable "node" -VersionCommand @("node", "--version") -MissingHint "Install Node.js."
Add-CommandCheck -Results $results -Name "npm" -Executable "npm" -VersionCommand @("npm", "--version") -MissingHint "Install npm together with Node.js."
Add-CommandCheck -Results $results -Name "docker" -Executable "docker" -VersionCommand @("docker", "--version") -MissingHint "Install Docker Desktop for local development."

$tesseractPath = ""
try {
    $tesseractProbe = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($tesseractProbe) {
        $tesseractPath = $tesseractProbe.Source
    }
    elseif (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") {
        $tesseractPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
    }
}
catch {
}

if (-not $tesseractPath) {
    $results.Add((New-CheckResult -Name "tesseract" -Status "warning" -Detail "not found" -Hint "Install Tesseract OCR if you want scanned PDFs and image OCR to work."))
}
else {
    $langs = ""
    try {
        $localTessdata = Join-RepoPath "data\app\ocr\tessdata"
        if (Test-Path $localTessdata) {
            $previousTessdataPrefix = $env:TESSDATA_PREFIX
            $env:TESSDATA_PREFIX = $localTessdata
        }
        $langOutput = & $tesseractPath --list-langs 2>$null
        $langs = (($langOutput | Select-Object -Skip 1) -join ", ").Trim()
    }
    catch {
    }
    finally {
        if (Test-Path variable:previousTessdataPrefix) {
            if ($null -eq $previousTessdataPrefix) {
                Remove-Item Env:TESSDATA_PREFIX -ErrorAction SilentlyContinue
            }
            else {
                $env:TESSDATA_PREFIX = $previousTessdataPrefix
            }
        }
    }

    $detail = if ($langs) { "available languages: $langs" } else { $tesseractPath }
    $results.Add((New-CheckResult -Name "tesseract" -Status "ok" -Detail $detail))
}

$envExamplePath = Join-RepoPath ".env.example"
$envPath = Join-RepoPath ".env"
if (Test-Path $envPath) {
    $results.Add((New-CheckResult -Name ".env" -Status "ok" -Detail "present"))
}
elseif (Test-Path $envExamplePath) {
    $results.Add((New-CheckResult -Name ".env" -Status "warning" -Detail "missing" -Hint "Copy `.env.example` to `.env` if you want a local env file as a setup reference."))
}
else {
    $results.Add((New-CheckResult -Name ".env" -Status "warning" -Detail "missing" -Hint "`.env.example` is missing too, so setup defaults are harder to inspect."))
}

$frontendNodeModules = Join-RepoPath "frontend\node_modules"
if (Test-Path $frontendNodeModules) {
    $results.Add((New-CheckResult -Name "frontend-packages" -Status "ok" -Detail "node_modules present"))
}
else {
    $results.Add((New-CheckResult -Name "frontend-packages" -Status "warning" -Detail "node_modules missing" -Hint "Run `npm install` inside `frontend/`."))
}

$backendImportCommand = @'
import os
import sys
from pathlib import Path
root = Path(r"__REPO_ROOT__")
sys.path.insert(0, str(root / "backend"))
import main
print("backend-import-ok")
'@

$backendImportScript = $backendImportCommand.Replace("__REPO_ROOT__", (Get-RepoRoot).Replace("\", "\\"))
try {
    $backendImportResult = $backendImportScript | py -3 -
    $detail = (($backendImportResult | Select-Object -First 1) -as [string]).Trim()
    if ($detail -eq "backend-import-ok") {
        $results.Add((New-CheckResult -Name "backend-import" -Status "ok" -Detail $detail))
    }
    else {
        if (-not $detail) {
            $detail = "unexpected output"
        }
        $results.Add((New-CheckResult -Name "backend-import" -Status "warning" -Detail $detail -Hint "Run `py -3 -m pip install -r backend/requirements.txt` if backend imports fail." ))
    }
}
catch {
    $results.Add((New-CheckResult -Name "backend-import" -Status "error" -Detail $_.Exception.Message -Hint "Run `py -3 -m pip install -r backend/requirements.txt` and retry."))
}

$runtimeUrls = Get-RuntimeUrls
$ollamaUrl = [string]$runtimeUrls.ollama_base_url
$qdrantUrl = [string]$runtimeUrls.qdrant_url

$ollamaProbe = Test-HttpEndpoint -Url "$ollamaUrl/api/tags"
if ($ollamaProbe.ok) {
    $results.Add((New-CheckResult -Name "ollama" -Status "ok" -Detail "$ollamaUrl/api/tags"))
}
else {
    $results.Add((New-CheckResult -Name "ollama" -Status "warning" -Detail "$ollamaUrl/api/tags -> $($ollamaProbe.detail)" -Hint "Start Ollama or update `OLLAMA_BASE_URL` / runtime settings if you use a remote host."))
}

$qdrantProbe = Test-HttpEndpoint -Url $qdrantUrl
if ($qdrantProbe.ok) {
    $results.Add((New-CheckResult -Name "qdrant" -Status "ok" -Detail $qdrantUrl))
}
else {
    $results.Add((New-CheckResult -Name "qdrant" -Status "warning" -Detail "$qdrantUrl -> $($qdrantProbe.detail)" -Hint "Run `./scripts/dev-up.ps1` for local development or verify the deployment stack."))
}

$summary = [pscustomobject]@{
    checked_at = (Get-Date).ToString("o")
    repo_root = Get-RepoRoot
    results = $results
}

if ($Json) {
    $summary | ConvertTo-Json -Depth 5
    exit 0
}

Write-Host ""
Write-Host "Local AI OS preflight" -ForegroundColor Cyan
Write-Host ""

foreach ($result in $results) {
    $prefix = switch ($result.status) {
        "ok" { "[OK] " }
        "warning" { "[WARN]" }
        default { "[ERR] " }
    }

    $color = switch ($result.status) {
        "ok" { "Green" }
        "warning" { "Yellow" }
        default { "Red" }
    }

    Write-Host "$prefix $($result.name): $($result.detail)" -ForegroundColor $color
    if ($result.hint) {
        Write-Host "      hint: $($result.hint)" -ForegroundColor DarkGray
    }
}

$errorCount = @($results | Where-Object { $_.status -eq "error" }).Count
$warningCount = @($results | Where-Object { $_.status -eq "warning" }).Count

Write-Host ""
Write-Host "Summary: $(@($results | Where-Object { $_.status -eq 'ok' }).Count) ok, $warningCount warnings, $errorCount errors."

if ($errorCount -gt 0) {
    exit 1
}

exit 0
