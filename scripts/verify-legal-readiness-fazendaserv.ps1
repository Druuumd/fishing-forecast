param(
    [string]$BaseUrl = "http://192.168.0.250:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking legal readiness on $BaseUrl ..." -ForegroundColor Cyan

$info = Invoke-RestMethod -Uri "$BaseUrl/v1/legal/info" -Method Get -TimeoutSec 10

function Test-Placeholder {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $true }
    $v = $Value.ToLowerInvariant()
    return $v.Contains("example.com") -or $v.Contains(".example") -or $v.Contains(".local")
}

$checks = [ordered]@{
    contact_email_set = -not (Test-Placeholder -Value $info.contact_email)
    support_email_set = -not (Test-Placeholder -Value $info.support_email)
    privacy_url_set = -not (Test-Placeholder -Value $info.privacy_url)
    terms_url_set = -not (Test-Placeholder -Value $info.terms_url)
    data_deletion_url_set = -not (Test-Placeholder -Value $info.data_deletion_url)
    cookie_tracking_url_set = -not (Test-Placeholder -Value $info.cookie_tracking_url)
}

$status = "ok"
if (($checks.GetEnumerator() | Where-Object { -not $_.Value }).Count -gt 0) {
    $status = "degraded"
}

$result = [ordered]@{
    status = $status
    legal_info = $info
    checks = $checks
}

Write-Host ($result | ConvertTo-Json -Depth 6)

if ($status -ne "ok") {
    exit 1
}
