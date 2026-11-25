# Stop local dev stack using logs/pids.json
$root = Split-Path -Parent $PSScriptRoot
$pidsFile = Join-Path $root "logs\pids.json"
if (Test-Path $pidsFile) {
    $pids = Get-Content $pidsFile -Raw | ConvertFrom-Json
    foreach ($name in $pids.PSObject.Properties.Name) {
        $procId = $pids.$name
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host ("stopped {0} (pid={1})" -f $name, $procId)
        }
    }
    Remove-Item $pidsFile -Force
} else {
    Write-Host "no pids.json, nothing to stop"
}
