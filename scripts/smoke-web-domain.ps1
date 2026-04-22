param(
    [string]$WebUrl = "https://kvh-forecast.ru",
    [string]$ApiUrl = "https://api.kvh-forecast.ru"
)

$ErrorActionPreference = "Stop"

function Assert-StatusCode {
    param(
        [string]$Url,
        [int]$Expected
    )
    $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 15 -UseBasicParsing
    if ([int]$response.StatusCode -ne $Expected) {
        throw "$Url returned $($response.StatusCode), expected $Expected"
    }
    return $response
}

Write-Host "Running web-domain smoke..." -ForegroundColor Cyan

$web = Assert-StatusCode -Url $WebUrl -Expected 200
if ($web.Content -notmatch "KVH Forecast Web") {
    throw "Web homepage content check failed"
}

$ready = Invoke-RestMethod -Uri "$ApiUrl/v1/ready" -Method Get -TimeoutSec 15
if ($ready.status -ne "ready") {
    throw "API ready check failed: $($ready | ConvertTo-Json -Compress)"
}

$health = Invoke-RestMethod -Uri "$ApiUrl/v1/health" -Method Get -TimeoutSec 15
if ($health.status -ne "ok") {
    throw "API health check failed: $($health | ConvertTo-Json -Compress)"
}

Write-Host "Web domain smoke passed." -ForegroundColor Green
