param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteDir = "/home/drumd/fishing-forecast"
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    ssh "$User@$RemoteHost" $Command
}

$compose = "docker compose -f docker-compose.yml -f docker-compose.stage.yml"
$startedAt = Get-Date
$rollbackSucceeded = $false
$candidateTag = "fishing-forecast-api:rehearsal-next"
$baselineTag = "fishing-forecast-api:rollback-baseline"

Write-Host "Starting rollback rehearsal on $RemoteHost ..." -ForegroundColor Cyan

$currentImageRaw = Invoke-Ssh "docker inspect fishing-forecast-api-1 --format '{{.Image}}'"
if ($null -eq $currentImageRaw) {
    throw "Cannot detect current api image id"
}
$currentImageId = $currentImageRaw.Trim()
if ([string]::IsNullOrWhiteSpace($currentImageId)) {
    throw "Cannot detect current api image id"
}

Write-Host "Current image:  $currentImageId"

try {
    Invoke-Ssh "docker tag $currentImageId $baselineTag"
    Invoke-Ssh "docker commit fishing-forecast-api-1 $candidateTag >/dev/null"
    $candidateImageId = (Invoke-Ssh "docker image inspect $candidateTag --format '{{.Id}}'").Trim()
    if ([string]::IsNullOrWhiteSpace($candidateImageId)) {
        throw "Cannot detect candidate rehearsal image id"
    }
    Write-Host "Candidate image: $candidateImageId"

    Invoke-Ssh "docker tag $candidateTag fishing-forecast-api:latest"
    Invoke-Ssh "cd $RemoteDir && $compose up -d api"
    Invoke-Ssh "curl -fsS http://127.0.0.1:8000/health >/dev/null && curl -fsS http://127.0.0.1:8000/ready >/dev/null"

    $runningCandidate = (Invoke-Ssh "docker inspect fishing-forecast-api-1 --format '{{.Image}}'").Trim()
    if ($runningCandidate -eq $currentImageId) {
        throw "Candidate rollout did not switch running image id"
    }

    Invoke-Ssh "docker tag $baselineTag fishing-forecast-api:latest"
    Invoke-Ssh "cd $RemoteDir && $compose up -d api"
    Invoke-Ssh "curl -fsS http://127.0.0.1:8000/health >/dev/null && curl -fsS http://127.0.0.1:8000/ready >/dev/null"
    $runningAfterRollback = (Invoke-Ssh "docker inspect fishing-forecast-api-1 --format '{{.Image}}'").Trim()
    if ($runningAfterRollback -ne $currentImageId) {
        throw "Rollback failed: running image id is not baseline"
    }

    $rollbackSucceeded = $true
} finally {
    Invoke-Ssh "docker tag $currentImageId fishing-forecast-api:latest"
    Invoke-Ssh "cd $RemoteDir && $compose up -d api"
    Invoke-Ssh "curl -fsS http://127.0.0.1:8000/health >/dev/null && curl -fsS http://127.0.0.1:8000/ready >/dev/null"
    Invoke-Ssh "docker image rm $candidateTag >/dev/null 2>&1 || true" | Out-Null
    Invoke-Ssh "docker image rm $baselineTag >/dev/null 2>&1 || true" | Out-Null
}

$elapsedSec = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
if (-not $rollbackSucceeded) {
    throw "Rollback step failed; service restored to current image, check logs"
}

Write-Host "Rollback rehearsal completed successfully." -ForegroundColor Green
Write-Host "Elapsed seconds: $elapsedSec"
