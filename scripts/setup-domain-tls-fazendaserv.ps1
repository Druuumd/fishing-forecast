param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteDir = "/home/drumd/fishing-forecast",
    [string]$Email = "admin@kvh-forecast.ru",
    [string]$SshKeyPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($SshKeyPath)) {
        ssh "$User@$RemoteHost" $Command
    } else {
        ssh -i $SshKeyPath "$User@$RemoteHost" $Command
    }
}

function Invoke-Scp {
    param(
        [string]$Source,
        [string]$Destination
    )
    if ([string]::IsNullOrWhiteSpace($SshKeyPath)) {
        scp $Source $Destination
    } else {
        scp -i $SshKeyPath $Source $Destination
    }
}

Write-Host "Configuring TLS certificates on fazendaserv ($RemoteHost)..." -ForegroundColor Cyan
Write-Host "Step 1: Ensure web nginx is running on localhost:8081." -ForegroundColor Yellow
Invoke-Ssh "cd $RemoteDir && docker compose -f docker-compose.yml -f docker-compose.stage.yml -f docker-compose.web.yml up -d nginx api"

Write-Host "Step 2: Patch Caddyfile with kvh domains and automatic TLS." -ForegroundColor Yellow
Invoke-Scp ".\infra\caddy\kvh-domain-block.caddy" "$User@$RemoteHost`:/tmp/kvh-domain-block.caddy"
Invoke-Scp ".\scripts\fazendaserv-patch-caddy.sh" "$User@$RemoteHost`:/tmp/fazendaserv-patch-caddy.sh"
Invoke-Ssh "sed -i 's/\r$//' /tmp/kvh-domain-block.caddy /tmp/fazendaserv-patch-caddy.sh && chmod +x /tmp/fazendaserv-patch-caddy.sh && /tmp/fazendaserv-patch-caddy.sh"

Write-Host "Step 3: Reload Caddy container." -ForegroundColor Yellow
Invoke-Ssh "docker restart caddy"

Write-Host "Caddy domain setup completed. Verify with:" -ForegroundColor Green
Write-Host "  https://kvh-forecast.ru" -ForegroundColor Green
Write-Host "  https://api.kvh-forecast.ru/v1/ready" -ForegroundColor Green
