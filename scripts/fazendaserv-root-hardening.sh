#!/usr/bin/env bash
set -euo pipefail

echo "[hardening] starting root host hardening..."

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[hardening] error: run as root (sudo -i)." >&2
  exit 1
fi

apt-get update
apt-get install -y fail2ban ufw unattended-upgrades

systemctl enable --now fail2ban unattended-upgrades ufw docker

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 8000/tcp
ufw --force enable

if grep -qE '^[#[:space:]]*PasswordAuthentication' /etc/ssh/sshd_config; then
  sed -i 's/^[#[:space:]]*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
else
  echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
fi

if grep -qE '^[#[:space:]]*PubkeyAuthentication' /etc/ssh/sshd_config; then
  sed -i 's/^[#[:space:]]*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
else
  echo "PubkeyAuthentication yes" >> /etc/ssh/sshd_config
fi

if grep -qE '^[#[:space:]]*PermitRootLogin' /etc/ssh/sshd_config; then
  sed -i 's/^[#[:space:]]*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
else
  echo "PermitRootLogin no" >> /etc/ssh/sshd_config
fi

if systemctl status ssh >/dev/null 2>&1; then
  systemctl restart ssh
else
  systemctl restart sshd
fi

echo "[hardening] done. effective state:"
systemctl is-active fail2ban
systemctl is-enabled fail2ban
systemctl is-active unattended-upgrades
systemctl is-enabled unattended-upgrades
systemctl is-active ufw
systemctl is-enabled ufw
grep -E '^(PasswordAuthentication|PubkeyAuthentication|PermitRootLogin)' /etc/ssh/sshd_config || true
