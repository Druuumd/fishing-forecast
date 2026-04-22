param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Username = "demo",
    [string]$Password = "demo123"
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    ssh "$User@$RemoteHost" $Command
}

$cronLineIngest = "10 3 * * * /bin/bash -lc ""token=`$(curl -fsS -X POST $BaseUrl/v1/auth/login -H 'Content-Type: application/json' -d '{\""username\"":\""${Username}\"",\""password\"":\""${Password}\""}' | python3 -c 'import sys,json; print(json.load(sys.stdin).get(""access_token"",""""))'); [ -n ""`$token"" ] && curl -fsS -X POST $BaseUrl/v1/admin/ingest/weather -H ""Authorization: Bearer `$token"" >/dev/null"""
$cronLineDq = "15 3 * * * /bin/bash -lc ""token=`$(curl -fsS -X POST $BaseUrl/v1/auth/login -H 'Content-Type: application/json' -d '{\""username\"":\""${Username}\"",\""password\"":\""${Password}\""}' | python3 -c 'import sys,json; print(json.load(sys.stdin).get(""access_token"",""""))'); [ -n ""`$token"" ] && curl -fsS $BaseUrl/v1/admin/dq/weather -H ""Authorization: Bearer `$token"" >/tmp/ff_weather_dq_last.json || echo weather_dq_failed >&2"""
$cronLineMl = "25 3 * * * /bin/bash -lc ""token=`$(curl -fsS -X POST $BaseUrl/v1/auth/login -H 'Content-Type: application/json' -d '{\""username\"":\""${Username}\"",\""password\"":\""${Password}\""}' | python3 -c 'import sys,json; print(json.load(sys.stdin).get(""access_token"",""""))'); [ -n ""`$token"" ] && curl -fsS -X POST $BaseUrl/v1/admin/ml/retrain -H ""Authorization: Bearer `$token"" >/tmp/ff_ml_retrain_last.json || echo ml_retrain_failed >&2"""
$tmpLocal = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpLocal -Value @($cronLineIngest, $cronLineDq, $cronLineMl)

Write-Host "Installing weather ingest cron on $RemoteHost ..." -ForegroundColor Cyan
scp $tmpLocal "$User@$RemoteHost`:/tmp/ff_ingest_cron_new.txt"
Invoke-Ssh "sed 's/\r$//' /tmp/ff_ingest_cron_new.txt > /tmp/ff_ingest_cron_new_lf.txt && echo >> /tmp/ff_ingest_cron_new_lf.txt && (crontab -l 2>/dev/null | sed 's/\r$//' | sed '\|/v1/admin/ingest/weather|d' | sed '\|/v1/admin/dq/weather|d' | sed '\|/v1/admin/ml/retrain|d'; cat /tmp/ff_ingest_cron_new_lf.txt) > /tmp/ff_ingest_cron_merged.txt && crontab /tmp/ff_ingest_cron_merged.txt && rm -f /tmp/ff_ingest_cron_new.txt /tmp/ff_ingest_cron_new_lf.txt /tmp/ff_ingest_cron_merged.txt"
Remove-Item $tmpLocal -ErrorAction SilentlyContinue
$resultingCrontab = Invoke-Ssh "crontab -l"
Write-Host $resultingCrontab
Write-Host "Crons installed (03:10 ingest, 03:15 DQ, 03:25 ML retrain)." -ForegroundColor Green
