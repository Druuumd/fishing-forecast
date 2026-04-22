param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd"
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "$User@$RemoteHost" $Command
}

Write-Host "Applying host hardening on $RemoteHost ..." -ForegroundColor Cyan

$sudoCheck = (Invoke-Ssh "sudo -n true >/dev/null 2>&1 && echo ok || echo no").Trim()

if ($sudoCheck -ne "ok") {
    Write-Host "Passwordless sudo is not available for $User." -ForegroundColor Yellow
    Write-Host "Run these commands on fazendaserv under root/sudo session:" -ForegroundColor Yellow
    Write-Host "  sudo apt-get update && sudo apt-get install -y fail2ban ufw unattended-upgrades"
    Write-Host "  sudo systemctl enable --now fail2ban unattended-upgrades ufw"
    Write-Host "  sudo ufw default deny incoming"
    Write-Host "  sudo ufw default allow outgoing"
    Write-Host "  sudo ufw allow 22/tcp"
    Write-Host "  sudo ufw allow 8000/tcp"
    Write-Host "  sudo ufw --force enable"
    Write-Host "  sudo sed -i 's/^#\\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config"
    Write-Host "  sudo sed -i 's/^#\\?PubkeyAuthentication .*/PubkeyAuthentication yes/' /etc/ssh/sshd_config"
    Write-Host "  sudo sed -i 's/^#\\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config"
    Write-Host "  sudo systemctl restart ssh || sudo systemctl restart sshd"
    exit 2
}

Invoke-Ssh "sudo apt-get update && sudo apt-get install -y fail2ban ufw unattended-upgrades"
Invoke-Ssh "sudo systemctl enable --now fail2ban unattended-upgrades ufw"
Invoke-Ssh "sudo ufw default deny incoming"
Invoke-Ssh "sudo ufw default allow outgoing"
Invoke-Ssh "sudo ufw allow 22/tcp"
Invoke-Ssh "sudo ufw allow 8000/tcp"
Invoke-Ssh "sudo ufw --force enable"
Invoke-Ssh "sudo sed -i 's/^#\\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config"
Invoke-Ssh "sudo sed -i 's/^#\\?PubkeyAuthentication .*/PubkeyAuthentication yes/' /etc/ssh/sshd_config"
Invoke-Ssh "sudo sed -i 's/^#\\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config"
Invoke-Ssh "sudo systemctl restart ssh || sudo systemctl restart sshd"

Write-Host "Host hardening commands completed." -ForegroundColor Green
