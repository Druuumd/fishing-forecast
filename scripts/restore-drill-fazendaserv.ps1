param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$BackupDir = "/home/drumd/fishing-forecast/backups/db"
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    ssh "$User@$RemoteHost" $Command
}

$startedAt = Get-Date
$containerName = "ff-restore-drill-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"

try {
    $latestBackup = (Invoke-Ssh "ls -1t $BackupDir/forecast_*.dump 2>/dev/null | head -n 1").Trim()
    if ([string]::IsNullOrWhiteSpace($latestBackup)) {
        throw "No backup file found in $BackupDir"
    }

    $backupFileName = [System.IO.Path]::GetFileName($latestBackup)
    Write-Host "Running restore drill from $backupFileName on $RemoteHost ..." -ForegroundColor Cyan

    Invoke-Ssh "docker rm -f $containerName >/dev/null 2>&1 || true"
    Invoke-Ssh "docker run -d --name $containerName -e POSTGRES_DB=restore_drill -e POSTGRES_USER=restore -e POSTGRES_PASSWORD=restore -v ${BackupDir}:/backups postgres:16-alpine >/dev/null"

    Invoke-Ssh "i=0; while [ `$i -lt 60 ]; do docker exec $containerName pg_isready -U restore -d restore_drill >/dev/null 2>&1 && exit 0; i=`$((i+1)); sleep 1; done; exit 1"

    Invoke-Ssh "docker exec $containerName pg_restore -U restore -d restore_drill --clean --if-exists --no-owner --no-privileges /backups/$backupFileName >/dev/null"
    $records = (Invoke-Ssh "docker exec $containerName psql -U restore -d restore_drill -Atc 'select count(*) from catch_records;'").Trim()

    $elapsedSec = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 1)
    Write-Host "Restore drill completed." -ForegroundColor Green
    Write-Host "Backup file: $backupFileName"
    Write-Host "catch_records count: $records"
    Write-Host "Elapsed seconds: $elapsedSec"
} finally {
    Invoke-Ssh "docker rm -f $containerName >/dev/null 2>&1 || true" | Out-Null
}
