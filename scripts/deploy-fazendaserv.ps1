param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteDir = "/home/drumd/fishing-forecast",
    [string]$SshKeyPath = "",
    [switch]$SkipWebBuild = $false
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param(
        [string]$Command
    )
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
        scp -r $Source $Destination
    } else {
        scp -i $SshKeyPath -r $Source $Destination
    }
}

Write-Host "Deploying to fazendaserv ($RemoteHost)..." -ForegroundColor Cyan

Invoke-Ssh "mkdir -p $RemoteDir"

if (-not $SkipWebBuild) {
    Write-Host "Building web frontend (React + Vite)..." -ForegroundColor Cyan
    Push-Location "web"
    try {
        if (-not (Test-Path "node_modules")) {
            npm install
        }
        npm run build
    } finally {
        Pop-Location
    }
}

$itemsToCopy = @(
    "backend",
    "docker-compose.yml",
    "docker-compose.stage.yml",
    "docker-compose.web.yml",
    ".env.stage.example",
    "infra"
)

foreach ($item in $itemsToCopy) {
    Invoke-Scp $item "$User@$RemoteHost`:$RemoteDir/"
}

Invoke-Ssh "mkdir -p $RemoteDir/web"
Invoke-Scp "web/dist" "$User@$RemoteHost`:$RemoteDir/web/"
Invoke-Ssh "chmod -R a+rX $RemoteDir/web/dist"
Invoke-Ssh "cd $RemoteDir && docker compose -f docker-compose.yml -f docker-compose.stage.yml -f docker-compose.web.yml up --build -d"
Invoke-Ssh "cd $RemoteDir && docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic upgrade head"

Write-Host "Deployment complete. Verifying remote endpoints..." -ForegroundColor Cyan
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\scripts\verify-gate1.ps1" -ForegroundColor Yellow
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\scripts\setup-domain-tls-fazendaserv.ps1 (configure Caddy domains)" -ForegroundColor Yellow
