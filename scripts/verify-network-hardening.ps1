param(
    [string]$TargetHost = "192.168.0.250"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking network hardening on $TargetHost" -ForegroundColor Cyan

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 2500
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $result = $client.BeginConnect($HostName, $Port, $null, $null)
        $success = $result.AsyncWaitHandle.WaitOne($TimeoutMs)
        if (-not $success) {
            return $false
        }
        $client.EndConnect($result)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$apiOpen = Test-TcpPort -HostName $TargetHost -Port 8000
$dbOpen = Test-TcpPort -HostName $TargetHost -Port 5432
$redisOpen = Test-TcpPort -HostName $TargetHost -Port 6379

if (-not $apiOpen) {
    Write-Error "API port 8000 is not reachable"
    exit 1
}

if ($dbOpen) {
    Write-Error "PostgreSQL port 5432 is externally reachable, expected closed"
    exit 1
}

if ($redisOpen) {
    Write-Error "Redis port 6379 is externally reachable, expected closed"
    exit 1
}

Write-Host "Network hardening checks passed." -ForegroundColor Green
Write-Host "8000/tcp: open (expected)"
Write-Host "5432/tcp: closed (expected)"
Write-Host "6379/tcp: closed (expected)"
