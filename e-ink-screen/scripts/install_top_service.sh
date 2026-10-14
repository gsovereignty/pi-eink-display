#!/bin/sh
set -eu
test "$(id -u)" = 0 || { echo 'Run via sudo'; exit 1; }
target_user="${1:-${SUDO_USER:-gareth}}"
target_group=$(id -gn "$target_user")
target_home=$(getent passwd "$target_user" | cut -d: -f6)
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test -f "$project_dir/config/inspection.json" || { echo 'Inspection confirmation missing'; exit 1; }
getent group gpio >/dev/null
getent group spi >/dev/null
install -d -o "$target_user" -g "$target_group" -m 0755 "$target_home/.local/state/eink-top"
unit_temp=$(mktemp -d)
trap 'rm -rf "$unit_temp"' EXIT HUP INT TERM
cat > "$unit_temp/eink-top.service" <<EOF
[Unit]
Description=E-paper top process monitor (ten-second averages)
After=local-fs.target systemd-udev-trigger.service

[Service]
Type=simple
User=$target_user
Group=$target_group
SupplementaryGroups=gpio spi
WorkingDirectory=$project_dir
ExecStart=/usr/bin/python3 -m hink_diag.top_display --hardware --inspection "$project_dir/config/inspection.json" --state-dir "$target_home/.local/state/eink-top"
Environment=PYTHONUNBUFFERED=1
Restart=no
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=eink-top

[Install]
WantedBy=multi-user.target
EOF
systemd-analyze verify "$unit_temp/eink-top.service"
if test -e /etc/systemd/system/eink-top.service; then
    cp -p /etc/systemd/system/eink-top.service "/etc/systemd/system/eink-top.service.backup-$(date +%s)"
fi
install -m 0644 "$unit_temp/eink-top.service" /etc/systemd/system/eink-top.service
systemctl daemon-reload
systemctl enable --now eink-top.service
systemctl status eink-top.service --no-pager
