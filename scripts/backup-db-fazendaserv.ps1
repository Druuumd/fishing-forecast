param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteDir = "/home/drumd/fishing-forecast",
    [string]$BackupDir = "/home/drumd/fishing-forecast/backups/db",
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    ssh "$User@$RemoteHost" $Command
}

$compose = "docker compose -f docker-compose.yml -f docker-compose.stage.yml"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$fileName = "forecast_$timestamp.dump"
$remoteBackupFile = "$BackupDir/$fileName"

Write-Host "Running DB backup on $RemoteHost ..." -ForegroundColor Cyan
Invoke-Ssh "mkdir -p $BackupDir"
Invoke-Ssh "cd $RemoteDir && $compose exec -T db pg_dump -U forecast -d forecast -Fc > $remoteBackupFile"
Invoke-Ssh "test -s $remoteBackupFile"
Invoke-Ssh "docker run --rm -v ${BackupDir}:/backups postgres:16-alpine pg_restore --list /backups/$fileName >/dev/null"
Invoke-Ssh "find $BackupDir -type f -name 'forecast_*.dump' -mtime +$RetentionDays -delete"

Write-Host "Backup completed: $remoteBackupFile" -ForegroundColor Green
