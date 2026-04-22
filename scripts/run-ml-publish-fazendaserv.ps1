param(
    [string]$BaseUrl = "http://192.168.0.250:8000",
    [string]$Username = "demo",
    [string]$Password = "demo123",
    [string]$ModelId = ""
)

$ErrorActionPreference = "Stop"

Write-Host "Publishing ML model on $BaseUrl ..." -ForegroundColor Cyan

$loginBody = @{
    username = $Username
    password = $Password
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri "$BaseUrl/v1/auth/login" -Method Post -TimeoutSec 10 -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)" }

$uri = "$BaseUrl/v1/admin/ml/publish"
if (-not [string]::IsNullOrWhiteSpace($ModelId)) {
    $uri = "$uri?model_id=$ModelId"
}

$result = Invoke-RestMethod -Uri $uri -Method Post -TimeoutSec 20 -Headers $headers
Write-Host ($result | ConvertTo-Json -Depth 8 -Compress)
