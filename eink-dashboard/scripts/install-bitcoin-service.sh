#!/bin/sh
# Install already-built applications; never installs dependencies or changes wiring.
set -eu
test "$(id -u)" = 0 || { echo 'Run via sudo'; exit 1; }
target_user="${1:-${SUDO_USER:-gareth}}"
target_group=$(id -gn "$target_user")
target_home=$(getent passwd "$target_user" | cut -d: -f6)
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python="$project_dir/.venv/bin/python"
inspection="$target_home/.config/eink-dashboard/inspection.json"
test -x "$python" || { echo 'Install dashboard and driver into .venv first'; exit 1; }
test -f "$inspection" || { echo 'Inspection confirmation missing'; exit 1; }
"$python" -c 'from epaper_dashboard.app import check_inspection; import sys; check_inspection(sys.argv[1])' "$inspection"
getent group gpio >/dev/null
getent group spi >/dev/null
install -d -o "$target_user" -g "$target_group" -m 0755 "$target_home/.local/state/eink-bitcoin"
unit_temp=$(mktemp -d)
trap 'rm -rf "$unit_temp"' EXIT HUP INT TERM
cat > "$unit_temp/eink-bitcoin.service" <<EOF
[Unit]
Description=Bitcoin mainnet e-paper dashboard
After=local-fs.target systemd-udev-trigger.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$target_user
Group=$target_group
SupplementaryGroups=gpio spi
WorkingDirectory=$target_home
ExecStart="$python" -m epaper_dashboard.bitcoin --hardware --inspection "$inspection" --state-dir "$target_home/.local/state/eink-bitcoin"
Environment=PYTHONUNBUFFERED=1
Environment=TZ=Asia/Shanghai
Restart=no
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=eink-bitcoin

[Install]
WantedBy=multi-user.target
EOF
systemd-analyze verify "$unit_temp/eink-bitcoin.service"
if test -e /etc/systemd/system/eink-bitcoin.service; then
    cp -p /etc/systemd/system/eink-bitcoin.service "/etc/systemd/system/eink-bitcoin.service.backup-$(date +%s)"
fi
# One owner only. Preserve original diagnostics and old unit for rollback.
if systemctl cat eink-top.service >/dev/null 2>&1; then
    systemctl disable --now eink-top.service
fi
if systemctl cat eink-dashboard.service >/dev/null 2>&1; then
    systemctl disable --now eink-dashboard.service
fi
install -m 0644 "$unit_temp/eink-bitcoin.service" /etc/systemd/system/eink-bitcoin.service
systemctl daemon-reload
systemctl enable --now eink-bitcoin.service
systemctl status eink-bitcoin.service --no-pager
