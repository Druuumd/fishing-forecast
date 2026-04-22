param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteScriptPath = "/tmp/fazendaserv-root-hardening.sh"
)

$ErrorActionPreference = "Stop"

Write-Host "Uploading root hardening script to $RemoteHost ..." -ForegroundColor Cyan
scp ".\scripts\fazendaserv-root-hardening.sh" "$User@$RemoteHost`:$RemoteScriptPath"
ssh "$User@$RemoteHost" "sed -i 's/\r$//' $RemoteScriptPath && chmod +x $RemoteScriptPath"

Write-Host "Script uploaded." -ForegroundColor Green
Write-Host "Run this command in an interactive root/sudo session on fazendaserv:"
Write-Host "  sudo bash $RemoteScriptPath"
Write-Host ""
Write-Host "Then verify from local machine:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\verify-bootstrap-security-fazendaserv.ps1"
