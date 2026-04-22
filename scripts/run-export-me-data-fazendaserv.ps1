param(
    [string]$BaseUrl = "http://192.168.0.250:8000",
    [string]$Username = "demo",
    [string]$Password = "demo123"
)

$ErrorActionPreference = "Stop"

Write-Host "Running self data export flow on $BaseUrl ..." -ForegroundColor Cyan

$loginBody = @{
    username = $Username
    password = $Password
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri "$BaseUrl/v1/auth/login" -Method Post -TimeoutSec 10 -ContentType "application/json" -Body $loginBody
$token = $login.access_token
$raw = curl.exe --max-time 20 -sS "$BaseUrl/v1/me/data" -H "Authorization: Bearer $token"
$result = $raw | ConvertFrom-Json
Write-Host ($result | ConvertTo-Json -Depth 8 -Compress)

if ($result.status -ne "ok" -or -not $result.user_id) {
    Write-Error "Export flow failed"
    exit 1
}
