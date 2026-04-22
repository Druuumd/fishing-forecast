param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd"
)

$ErrorActionPreference = "Stop"

function Invoke-Ssh {
    param([string]$Command)
    ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "$User@$RemoteHost" $Command
}

Write-Host "Verifying bootstrap/security baseline on $RemoteHost ..." -ForegroundColor Cyan

$dockerActive = (Invoke-Ssh "systemctl is-active docker").Trim()
$dockerEnabled = (Invoke-Ssh "systemctl is-enabled docker").Trim()
$fail2banActive = (Invoke-Ssh "systemctl is-active fail2ban").Trim()
$fail2banEnabled = (Invoke-Ssh "systemctl is-enabled fail2ban").Trim()
$upgradesActive = (Invoke-Ssh "systemctl is-active unattended-upgrades").Trim()
$upgradesEnabled = (Invoke-Ssh "systemctl is-enabled unattended-upgrades").Trim()
$ufwActive = (Invoke-Ssh "systemctl is-active ufw").Trim()
$ufwEnabled = (Invoke-Ssh "systemctl is-enabled ufw").Trim()

$sshdRaw = Invoke-Ssh "grep -E '^(PasswordAuthentication|PubkeyAuthentication|PermitRootLogin)' /etc/ssh/sshd_config || true"
$sshdMap = @{}
foreach ($line in ($sshdRaw -split "`n")) {
    $trimmed = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
    $parts = $trimmed -split "\s+", 2
    if ($parts.Count -eq 2) {
        $sshdMap[$parts[0]] = $parts[1].ToLowerInvariant()
    }
}

$checks = [ordered]@{
    docker_active = ($dockerActive -eq "active")
    docker_enabled = ($dockerEnabled -eq "enabled")
    fail2ban_active = ($fail2banActive -eq "active")
    fail2ban_enabled = ($fail2banEnabled -eq "enabled")
    unattended_upgrades_active = ($upgradesActive -eq "active")
    unattended_upgrades_enabled = ($upgradesEnabled -eq "enabled")
    ufw_active = ($ufwActive -eq "active")
    ufw_enabled = ($ufwEnabled -eq "enabled")
    ssh_permit_root_login_no = ($sshdMap["PermitRootLogin"] -eq "no")
    ssh_pubkey_auth_yes = ($sshdMap["PubkeyAuthentication"] -eq "yes")
    ssh_password_auth_no = ($sshdMap["PasswordAuthentication"] -eq "no")
}

$status = "ok"
if (($checks.GetEnumerator() | Where-Object { -not $_.Value }).Count -gt 0) {
    $status = "degraded"
}

$result = [ordered]@{
    status = $status
    host = $RemoteHost
    checks = $checks
    sshd_effective = [ordered]@{
        PermitRootLogin = $sshdMap["PermitRootLogin"]
        PubkeyAuthentication = $sshdMap["PubkeyAuthentication"]
        PasswordAuthentication = $sshdMap["PasswordAuthentication"]
    }
}

Write-Host ($result | ConvertTo-Json -Depth 6)

if ($status -ne "ok") {
    exit 1
}
