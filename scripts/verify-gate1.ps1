param(
    [string]$BaseUrl = "http://192.168.0.250:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking Gate 1 readiness against $BaseUrl" -ForegroundColor Cyan

try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get -TimeoutSec 5
    $ready = Invoke-RestMethod -Uri "$BaseUrl/ready" -Method Get -TimeoutSec 5
} catch {
    Write-Error "API is not reachable: $($_.Exception.Message)"
    exit 1
}

if ($health.status -ne "ok") {
    Write-Error "Health check failed: $($health | ConvertTo-Json -Compress)"
    exit 1
}

if ($ready.status -ne "ready") {
    Write-Error "Readiness check failed: $($ready | ConvertTo-Json -Compress)"
    exit 1
}

Write-Host "Gate 1 API checks passed." -ForegroundColor Green
Write-Host "Health: $($health | ConvertTo-Json -Compress)"
Write-Host "Ready:  $($ready  | ConvertTo-Json -Compress)"
