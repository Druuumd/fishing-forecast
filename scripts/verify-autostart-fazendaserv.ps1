param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteDir = "/home/drumd/fishing-forecast"
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "$User@$RemoteHost" $Command
}

Write-Host "Verifying autostart readiness on $RemoteHost ..." -ForegroundColor Cyan

$dockerActive = (Invoke-Ssh "systemctl is-active docker").Trim()
$dockerEnabled = (Invoke-Ssh "systemctl is-enabled docker").Trim()

$apiRestart = (Invoke-Ssh "docker inspect fishing-forecast-api-1 --format '{{.HostConfig.RestartPolicy.Name}}'").Trim()
$dbRestart = (Invoke-Ssh "docker inspect fishing-forecast-db-1 --format '{{.HostConfig.RestartPolicy.Name}}'").Trim()
$redisRestart = (Invoke-Ssh "docker inspect fishing-forecast-redis-1 --format '{{.HostConfig.RestartPolicy.Name}}'").Trim()

$apiStatus = (Invoke-Ssh "docker inspect fishing-forecast-api-1 --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}'").Trim()
$readyHttpCode = (Invoke-Ssh "curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/v1/ready").Trim()

$checks = [ordered]@{
    docker_active = ($dockerActive -eq "active")
    docker_enabled = ($dockerEnabled -eq "enabled")
    restart_policy_api = ($apiRestart -eq "unless-stopped")
    restart_policy_db = ($dbRestart -eq "unless-stopped")
    restart_policy_redis = ($redisRestart -eq "unless-stopped")
    api_running = ($apiStatus -like "running*")
    api_healthy = ($apiStatus -like "*|healthy")
    ready_local_ok = ($readyHttpCode -eq "200")
}

$status = "ok"
if (($checks.GetEnumerator() | Where-Object { -not $_.Value }).Count -gt 0) {
    $status = "degraded"
}

$result = [ordered]@{
    status = $status
    host = $RemoteHost
    checks = $checks
    details = [ordered]@{
        docker = [ordered]@{
            active = $dockerActive
            enabled = $dockerEnabled
        }
        restart_policy = [ordered]@{
            api = $apiRestart
            db = $dbRestart
            redis = $redisRestart
        }
        api_state = $apiStatus
        ready_http_code = $readyHttpCode
    }
}

Write-Host ($result | ConvertTo-Json -Depth 8)

if ($status -ne "ok") {
    exit 1
}
