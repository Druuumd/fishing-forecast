param(
    [string]$BaseUrl = "http://192.168.0.250:8000",
    [string]$Username = "demo",
    [string]$Password = "demo123"
)

$ErrorActionPreference = "Stop"

Write-Host "Triggering weather ingest on $BaseUrl ..." -ForegroundColor Cyan

$loginBody = @{
    username = $Username
    password = $Password
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri "$BaseUrl/v1/auth/login" -Method Post -TimeoutSec 10 -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)" }

$result = Invoke-RestMethod -Uri "$BaseUrl/v1/admin/ingest/weather" -Method Post -TimeoutSec 20 -Headers $headers
Write-Host ($result | ConvertTo-Json -Compress) -ForegroundColor Green
