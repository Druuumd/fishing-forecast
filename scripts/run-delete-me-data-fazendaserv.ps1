param(
    [string]$BaseUrl = "http://192.168.0.250:8000",
    [string]$Username = "demo",
    [string]$Password = "demo123"
)

$ErrorActionPreference = "Stop"

Write-Host "Running self data deletion flow on $BaseUrl ..." -ForegroundColor Cyan

$loginBody = @{
    username = $Username
    password = $Password
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri "$BaseUrl/v1/auth/login" -Method Post -TimeoutSec 10 -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)" }

$result = $null
$attempt = 0
while ($attempt -lt 3 -and $null -eq $result) {
    $attempt++
    try {
        $result = Invoke-RestMethod -Uri "$BaseUrl/v1/me/data" -Method Delete -TimeoutSec 20 -Headers $headers
    } catch {
        if ($attempt -ge 3) {
            throw
        }
        Start-Sleep -Seconds 2
    }
}
Write-Host ($result | ConvertTo-Json -Depth 6 -Compress)

if ($result.status -ne "ok") {
    Write-Error "Delete flow failed"
    exit 1
}
