param(
    [string]$BaseUrl = "http://192.168.0.250:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "Running smoke checks against $BaseUrl" -ForegroundColor Cyan

try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/v1/health" -Method Get -TimeoutSec 8
    $ready = Invoke-RestMethod -Uri "$BaseUrl/v1/ready" -Method Get -TimeoutSec 8
    $forecast = Invoke-RestMethod -Uri "$BaseUrl/v1/forecast?species=pike" -Method Get -TimeoutSec 8
} catch {
    Write-Error "Smoke request failed: $($_.Exception.Message)"
    exit 1
}

if ($health.status -ne "ok") {
    Write-Error "Health check failed: $($health | ConvertTo-Json -Compress)"
    exit 1
}

if ($ready.status -ne "ready") {
    Write-Error "Ready check failed: $($ready | ConvertTo-Json -Compress)"
    exit 1
}

if (-not $forecast.days -or $forecast.days.Count -lt 7) {
    Write-Error "Forecast response invalid: $($forecast | ConvertTo-Json -Depth 4 -Compress)"
    exit 1
}

$uniqueNote = "smoke-stage-" + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$payload = @{
    species = "perch"
    score = 4.0
    latitude = 55.99
    longitude = 92.88
    note = $uniqueNote
} | ConvertTo-Json

try {
    $loginBody = @{
        username = "demo"
        password = "demo123"
    } | ConvertTo-Json
    $login = Invoke-RestMethod -Uri "$BaseUrl/v1/auth/login" -Method Post -TimeoutSec 8 -ContentType "application/json" -Body $loginBody
    $authHeaders = @{ "Authorization" = "Bearer $($login.access_token)" }
    $created = Invoke-RestMethod -Uri "$BaseUrl/v1/catch" -Method Post -TimeoutSec 8 -Headers $authHeaders -ContentType "application/json" -Body $payload
    $consentBody = @{
        geo_allowed = $true
        push_allowed = $false
        analytics_allowed = $false
    } | ConvertTo-Json
    $consentUpdated = Invoke-RestMethod -Uri "$BaseUrl/v1/consent" -Method Put -TimeoutSec 8 -Headers $authHeaders -ContentType "application/json" -Body $consentBody
    $consentCurrent = Invoke-RestMethod -Uri "$BaseUrl/v1/consent/me" -Method Get -TimeoutSec 8 -Headers $authHeaders
} catch {
    Write-Error "Auth/catch/consent flow failed: $($_.Exception.Message)"
    exit 1
}

if (-not $created.id) {
    Write-Error "Catch response missing id: $($created | ConvertTo-Json -Compress)"
    exit 1
}

if (-not $consentUpdated.user_id -or $consentCurrent.geo_allowed -ne $true) {
    Write-Error "Consent flow failed: update=$($consentUpdated | ConvertTo-Json -Compress) current=$($consentCurrent | ConvertTo-Json -Compress)"
    exit 1
}

$noHeaderStatus = 0
try {
    Invoke-RestMethod -Uri "$BaseUrl/v1/catch" -Method Post -TimeoutSec 8 -ContentType "application/json" -Body $payload | Out-Null
    $noHeaderStatus = 200
} catch {
    if ($_.Exception.Response) {
        $noHeaderStatus = [int]$_.Exception.Response.StatusCode
    }
}

if ($noHeaderStatus -ne 401) {
    Write-Error "Expected 401 without bearer token, got: $noHeaderStatus"
    exit 1
}

Write-Host "Smoke checks passed." -ForegroundColor Green
Write-Host "Health:   $($health | ConvertTo-Json -Compress)"
Write-Host "Ready:    $($ready | ConvertTo-Json -Compress)"
Write-Host "Forecast: $($forecast.days.Count) days"
Write-Host "Catch ID: $($created.id)"
Write-Host "Consent:  geo=$($consentCurrent.geo_allowed) push=$($consentCurrent.push_allowed) analytics=$($consentCurrent.analytics_allowed)"
