param(
    [string]$RemoteHost = "192.168.0.250",
    [string]$User = "drumd",
    [string]$RemoteDir = "/home/drumd/fishing-forecast",
    [string]$RemoteEnvFile = ".env.stage.example",
    [string]$ContactEmail,
    [string]$SupportEmail,
    [string]$PrivacyUrl,
    [string]$TermsUrl,
    [string]$DataDeletionUrl,
    [string]$CookieTrackingUrl
)

$ErrorActionPreference = "Stop"

if (
    [string]::IsNullOrWhiteSpace($ContactEmail) -or
    [string]::IsNullOrWhiteSpace($SupportEmail) -or
    [string]::IsNullOrWhiteSpace($PrivacyUrl) -or
    [string]::IsNullOrWhiteSpace($TermsUrl) -or
    [string]::IsNullOrWhiteSpace($DataDeletionUrl) -or
    [string]::IsNullOrWhiteSpace($CookieTrackingUrl)
) {
    throw "All legal fields are required."
}

function Invoke-Ssh {
    param([string]$Command)
    ssh "$User@$RemoteHost" $Command
    if ($LASTEXITCODE -ne 0) {
        throw "SSH command failed: $Command"
    }
}

$tmp = [System.IO.Path]::GetTempFileName()
@(
    "LEGAL_CONTACT_EMAIL=$ContactEmail"
    "LEGAL_SUPPORT_EMAIL=$SupportEmail"
    "LEGAL_PRIVACY_URL=$PrivacyUrl"
    "LEGAL_TERMS_URL=$TermsUrl"
    "LEGAL_DATA_DELETION_URL=$DataDeletionUrl"
    "LEGAL_COOKIE_TRACKING_URL=$CookieTrackingUrl"
) | Set-Content -Path $tmp -NoNewline:$false

Write-Host "Uploading legal config patch to $RemoteHost ..." -ForegroundColor Cyan
scp $tmp "$User@$RemoteHost`:/tmp/ff_legal_env_patch.txt"
Remove-Item $tmp -ErrorAction SilentlyContinue

Invoke-Ssh "sed -i 's/\r$//' /tmp/ff_legal_env_patch.txt"
Invoke-Ssh "cd $RemoteDir && test -f $RemoteEnvFile"
Invoke-Ssh "cd $RemoteDir && sed -i '/^LEGAL_CONTACT_EMAIL=/d;/^LEGAL_SUPPORT_EMAIL=/d;/^LEGAL_PRIVACY_URL=/d;/^LEGAL_TERMS_URL=/d;/^LEGAL_DATA_DELETION_URL=/d;/^LEGAL_COOKIE_TRACKING_URL=/d' $RemoteEnvFile"
Invoke-Ssh "cd $RemoteDir && cat /tmp/ff_legal_env_patch.txt >> $RemoteEnvFile"
Invoke-Ssh "rm -f /tmp/ff_legal_env_patch.txt"

Write-Host "Legal config updated in $RemoteEnvFile on fazendaserv." -ForegroundColor Green
Write-Host "Next step:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\deploy-fazendaserv.ps1"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\verify-legal-readiness-fazendaserv.ps1"
