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

$cronLine = '0 3 * * * mkdir -p {0} && cd {1} && ts=$(date +\%Y\%m\%d_\%H\%M\%S) && docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T db pg_dump -U forecast -d forecast -Fc > {0}/forecast_$ts.dump && find {0} -type f -name ''forecast_*.dump'' -mtime +{2} -delete' -f $BackupDir, $RemoteDir, $RetentionDays
$tmpLocal = [System.IO.Path]::GetTempFileName()
Set-Content -Path $tmpLocal -Value $cronLine

Write-Host "Installing daily backup cron on $RemoteHost ..." -ForegroundColor Cyan
scp $tmpLocal "$User@$RemoteHost`:/tmp/ff_backup_cron_new.txt"
Invoke-Ssh "sed 's/\r$//' /tmp/ff_backup_cron_new.txt > /tmp/ff_backup_cron_new_lf.txt && echo >> /tmp/ff_backup_cron_new_lf.txt && (crontab -l 2>/dev/null | sed 's/\r$//' | sed '\|fishing-forecast/backups/db/forecast_|d'; sed -n '1p' /tmp/ff_backup_cron_new_lf.txt) > /tmp/ff_backup_cron_merged.txt && crontab /tmp/ff_backup_cron_merged.txt && rm -f /tmp/ff_backup_cron_new.txt /tmp/ff_backup_cron_new_lf.txt /tmp/ff_backup_cron_merged.txt"
Remove-Item $tmpLocal -ErrorAction SilentlyContinue
$resultingCrontab = Invoke-Ssh "crontab -l"
Write-Host $resultingCrontab

Write-Host "Cron installed (03:00 daily)." -ForegroundColor Green
