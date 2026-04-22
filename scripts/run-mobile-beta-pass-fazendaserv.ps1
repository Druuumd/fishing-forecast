param(
    [string]$BaseUrl = "http://192.168.0.250:8000",
    [string]$Username = "demo",
    [string]$Password = "demo123"
)

$ErrorActionPreference = "Stop"

function Invoke-TestCase {
    param(
        [string]$Id,
        [string]$Name,
        [scriptblock]$Action
    )
    try {
        & $Action
        return [ordered]@{ id = $Id; name = $Name; status = "PASS"; details = $null }
    } catch {
        return [ordered]@{ id = $Id; name = $Name; status = "FAIL"; details = $_.Exception.Message }
    }
}

Write-Host "Running mobile beta pass checks on $BaseUrl ..." -ForegroundColor Cyan

$loginBody = @{ username = $Username; password = $Password } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "$BaseUrl/v1/auth/login" -Method Post -TimeoutSec 10 -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)" }

$results = @()

$results += Invoke-TestCase -Id "TC-01" -Name "Login success" -Action {
    if (-not $login.access_token) { throw "access_token missing" }
}

$results += Invoke-TestCase -Id "TC-02" -Name "Forecast rendering" -Action {
    $f = Invoke-RestMethod -Uri "$BaseUrl/v1/forecast?species=pike" -Method Get -TimeoutSec 10
    if (-not $f.days -or $f.days.Count -lt 7) { throw "forecast days invalid" }
}

$results += Invoke-TestCase -Id "TC-03" -Name "Catch create" -Action {
    $payload = @{
        species = "perch"
        score = 4.0
        latitude = 55.99
        longitude = 92.88
        note = "mobile-beta-" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    } | ConvertTo-Json
    $c = Invoke-RestMethod -Uri "$BaseUrl/v1/catch" -Method Post -Headers $headers -ContentType "application/json" -Body $payload -TimeoutSec 10
    if (-not $c.id) { throw "catch id missing" }
}

$results += Invoke-TestCase -Id "TC-04" -Name "Consent roundtrip" -Action {
    $consent = @{ geo_allowed = $true; push_allowed = $false; analytics_allowed = $false } | ConvertTo-Json
    Invoke-RestMethod -Uri "$BaseUrl/v1/consent" -Method Put -Headers $headers -ContentType "application/json" -Body $consent -TimeoutSec 10 | Out-Null
    $current = Invoke-RestMethod -Uri "$BaseUrl/v1/consent/me" -Method Get -Headers $headers -TimeoutSec 10
    if ($current.geo_allowed -ne $true -or $current.push_allowed -ne $false -or $current.analytics_allowed -ne $false) {
        throw "consent values mismatch"
    }
}

$results += Invoke-TestCase -Id "TC-05" -Name "DSAR export" -Action {
    $exp = Invoke-RestMethod -Uri "$BaseUrl/v1/me/data" -Method Get -Headers $headers -TimeoutSec 10
    if ($exp.status -ne "ok" -or -not $exp.user_id) { throw "export invalid" }
}

$results += Invoke-TestCase -Id "TC-06" -Name "DSAR delete + empty export" -Action {
    $del = Invoke-RestMethod -Uri "$BaseUrl/v1/me/data" -Method Delete -Headers $headers -TimeoutSec 10
    if ($del.status -ne "ok") { throw "delete failed" }
    $exp2 = Invoke-RestMethod -Uri "$BaseUrl/v1/me/data" -Method Get -Headers $headers -TimeoutSec 10
    if ($exp2.catches.Count -ne 0) { throw "catches not empty after delete" }
}

$results += Invoke-TestCase -Id "TC-07" -Name "Legal links on kvh domain" -Action {
    $li = Invoke-RestMethod -Uri "$BaseUrl/v1/legal/info" -Method Get -TimeoutSec 10
    if (-not $li.privacy_url.Contains("kvh-forecast.ru")) { throw "privacy_url not kvh domain" }
    if (-not $li.terms_url.Contains("kvh-forecast.ru")) { throw "terms_url not kvh domain" }
    if (-not $li.contact_email.Contains("@kvh-forecast.ru")) { throw "contact_email not kvh domain" }
}

$results += Invoke-TestCase -Id "TC-08" -Name "Offline queue replay simulation" -Action {
    $queued = @(
        @{
            species = "pike"
            score = 3.7
            latitude = 56.01
            longitude = 92.93
            note = "mobile-offline-queue-" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        }
    )
    $sent = 0
    foreach ($item in $queued) {
        $payload = $item | ConvertTo-Json
        $c = Invoke-RestMethod -Uri "$BaseUrl/v1/catch" -Method Post -Headers $headers -ContentType "application/json" -Body $payload -TimeoutSec 10
        if (-not $c.id) { throw "queue replay catch id missing" }
        $sent += 1
    }
    if ($sent -ne $queued.Count) { throw "queue replay count mismatch" }
}

$results += Invoke-TestCase -Id "TC-09" -Name "Auth expiry handling (invalid token -> relogin)" -Action {
    $badHeaders = @{ Authorization = "Bearer invalid-token" }
    $unauthorized = $false
    try {
        Invoke-RestMethod -Uri "$BaseUrl/v1/consent/me" -Method Get -Headers $badHeaders -TimeoutSec 10 | Out-Null
    } catch {
        if ($_.Exception.Message -match "401" -or $_.Exception.Message -match "Unauthorized") {
            $unauthorized = $true
        } else {
            throw
        }
    }
    if (-not $unauthorized) { throw "expected 401 for invalid token" }

    $reloginBody = @{ username = $Username; password = $Password } | ConvertTo-Json
    $relogin = Invoke-RestMethod -Uri "$BaseUrl/v1/auth/login" -Method Post -TimeoutSec 10 -ContentType "application/json" -Body $reloginBody
    $retryHeaders = @{ Authorization = "Bearer $($relogin.access_token)" }
    $retry = Invoke-RestMethod -Uri "$BaseUrl/v1/consent/me" -Method Get -Headers $retryHeaders -TimeoutSec 10
    if (-not $retry.user_id) { throw "retry after relogin failed" }
}

$failed = @($results | Where-Object { $_.status -ne "PASS" })
$overall = if ($failed.Count -eq 0) { "PASS" } else { "FAIL" }

$report = [ordered]@{
    checked_at_utc = [DateTime]::UtcNow.ToString("o")
    base_url = $BaseUrl
    overall = $overall
    cases = $results
}

Write-Host ($report | ConvertTo-Json -Depth 8)

if ($overall -ne "PASS") {
    exit 1
}
