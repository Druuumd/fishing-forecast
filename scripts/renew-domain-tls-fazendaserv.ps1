param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteDir = "/home/drumd/fishing-forecast",
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

Write-Host "Renewing TLS certificates on fazendaserv ($RemoteHost)..." -ForegroundColor Cyan
Invoke-Ssh "docker restart caddy"
Write-Host "Renew/refresh done (Caddy handles automatic cert renewal)." -ForegroundColor Green
