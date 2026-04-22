param(
    [string]$LanBaseUrl = "http://192.168.0.250:8000",
    [string]$WanBaseUrl = "http://84.22.146.195:8000",
    [string]$WebDomainUrl = "https://kvh-forecast.ru",
    [string]$ApiDomainUrl = "https://api.kvh-forecast.ru",
    [switch]$EnableDomainChecks = $false
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    try {
        & $Action
        return [ordered]@{
            name = $Name
            status = "PASS"
            details = $null
        }
    } catch {
        return [ordered]@{
            name = $Name
            status = "FAIL"
            details = $_.Exception.Message
        }
    }
}

$results = @()

$results += Invoke-Step -Name "gate1_lan" -Action {
    powershell -ExecutionPolicy Bypass -File ".\scripts\verify-gate1.ps1" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "verify-gate1 failed with exit code $LASTEXITCODE" }
}

$results += Invoke-Step -Name "smoke_lan" -Action {
    powershell -ExecutionPolicy Bypass -File ".\scripts\smoke-stage.ps1" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "smoke-stage failed with exit code $LASTEXITCODE" }
}

$results += Invoke-Step -Name "network_hardening" -Action {
    powershell -ExecutionPolicy Bypass -File ".\scripts\verify-network-hardening.ps1" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "verify-network-hardening failed with exit code $LASTEXITCODE" }
}

$results += Invoke-Step -Name "weather_dq" -Action {
    powershell -ExecutionPolicy Bypass -File ".\scripts\run-weather-dq-fazendaserv.ps1" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "run-weather-dq failed with exit code $LASTEXITCODE" }
}

$results += Invoke-Step -Name "ml_active_exists" -Action {
    $out = powershell -ExecutionPolicy Bypass -File ".\scripts\run-ml-active-fazendaserv.ps1" | Out-String
    if ($LASTEXITCODE -ne 0) { throw "run-ml-active failed with exit code $LASTEXITCODE" }
    if ($out -notmatch '"model"') {
        throw "active model not found"
    }
}

$results += Invoke-Step -Name "dsar_delete_me_data" -Action {
    powershell -ExecutionPolicy Bypass -File ".\scripts\run-delete-me-data-fazendaserv.ps1" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "run-delete-me-data failed with exit code $LASTEXITCODE" }
}

$results += Invoke-Step -Name "dsar_export_me_data" -Action {
    powershell -ExecutionPolicy Bypass -File ".\scripts\run-export-me-data-fazendaserv.ps1" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "run-export-me-data failed with exit code $LASTEXITCODE" }
}

$results += Invoke-Step -Name "wan_health" -Action {
    $health = curl.exe --max-time 12 -sS "$WanBaseUrl/health"
    if ($health -notmatch '"status":"ok"') {
        throw "unexpected response: $health"
    }
}

$results += Invoke-Step -Name "wan_ready" -Action {
    $ready = curl.exe --max-time 12 -sS "$WanBaseUrl/ready"
    if ($ready -notmatch '"status":"ready"') {
        throw "unexpected response: $ready"
    }
}

if ($EnableDomainChecks) {
    $results += Invoke-Step -Name "domain_web_smoke" -Action {
        powershell -ExecutionPolicy Bypass -File ".\scripts\smoke-web-domain.ps1" -WebUrl $WebDomainUrl -ApiUrl $ApiDomainUrl | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "smoke-web-domain failed with exit code $LASTEXITCODE" }
    }
}

$failed = @($results | Where-Object { $_.status -ne "PASS" })
$overall = if ($failed.Count -eq 0) { "PASS" } else { "FAIL" }

$report = [ordered]@{
    checked_at_utc = [DateTime]::UtcNow.ToString("o")
    lan_base_url = $LanBaseUrl
    wan_base_url = $WanBaseUrl
    overall = $overall
    steps = $results
}

Write-Host ($report | ConvertTo-Json -Depth 6)

if ($overall -ne "PASS") {
    exit 1
}
