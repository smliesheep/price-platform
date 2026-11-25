# Local dev stack: postgres/redis containers + mock-shop + api + scheduler + reaper + worker
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev_up.ps1 [-SkipWorker]
param(
    [switch]$SkipWorker
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

Write-Host "==> docker compose up (postgres/redis)"
docker compose -f deploy/compose/docker-compose.dev.yml up -d postgres redis | Out-Null

function Start-Svc {
    param([string]$Name, [string[]]$ArgList, [hashtable]$Env = @{}, [string]$WorkDir = $root)
    $out = Join-Path $logs "$Name.out.log"
    $err = Join-Path $logs "$Name.err.log"
    $saved = @{}
    foreach ($k in $Env.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k, "Process")
        [Environment]::SetEnvironmentVariable($k, $Env[$k], "Process")
    }
    $p = Start-Process -FilePath $py -ArgumentList $ArgList -WorkingDirectory $WorkDir -WindowStyle Hidden `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    foreach ($k in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($k, $saved[$k], "Process")
    }
    Write-Host ("    {0,-10} pid={1}" -f $Name, $p.Id)
    return $p.Id
}

$pids = @{}
$pids["mock-shop"] = Start-Svc -Name "mock-shop" -ArgList @("-u","-m","uvicorn","app:app","--host","127.0.0.1","--port","8088") -WorkDir (Join-Path $root "mock-shop")
$pids["api"] = Start-Svc -Name "api" -ArgList @("-u","-m","uvicorn","price_platform.api.main:app","--host","127.0.0.1","--port","8000")
$pids["scheduler"] = Start-Svc -Name "scheduler" -ArgList @("-u","-m","price_platform.scheduler.main") -Env @{ "PP_METRICS_PORT" = "9101" }
$pids["reaper"] = Start-Svc -Name "reaper" -ArgList @("-u","-m","price_platform.reaper.main") -Env @{ "PP_METRICS_PORT" = "9102" }
if (-not $SkipWorker) {
    $pids["worker"] = Start-Svc -Name "worker" -ArgList @("-u","-m","price_platform.worker.main") -Env @{ "PP_METRICS_PORT" = "9103" }
}

$pids | ConvertTo-Json | Set-Content (Join-Path $logs "pids.json") -Encoding UTF8
Start-Sleep -Seconds 6
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -TimeoutSec 5
    Write-Host ("==> api healthy: " + ($health | ConvertTo-Json -Compress))
} catch {
    Write-Host "==> api not healthy yet, check logs/*.err.log"
}
