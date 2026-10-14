#!/bin/sh
# Root-owned fixed-purpose helpers; preserve existing host networking.
set -eu
test "$(id -u)" = 0
install -d -m 0755 /usr/local/lib/pi-codex
install -m 0755 /tmp/refresh-routes.py /usr/local/lib/pi-codex/refresh-routes.py
install -m 0755 /home/gareth/git/hardware/eink-codex/scripts/network-status.py /usr/local/lib/pi-codex/network-status.py
cat > /etc/systemd/system/pi-codex-routes.service <<'EOF'
[Unit]
Description=Refresh selected OpenAI WireGuard routes
After=wg-quick@ivpn-openai.service network-online.target
Requires=wg-quick@ivpn-openai.service
[Service]
Type=oneshot
ExecStart=/usr/local/lib/pi-codex/refresh-routes.py
TimeoutStartSec=90
EOF
cat > /etc/systemd/system/pi-codex-routes.timer <<'EOF'
[Unit]
Description=Refresh selected OpenAI IPv4 routes every 15 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/pi-codex-network-status.service <<'EOF'
[Unit]
Description=Export WireGuard and Nostrocket connection state
After=wg-quick@ivpn-openai.service zerotier-one.service
[Service]
Type=oneshot
ExecStart=/usr/local/lib/pi-codex/network-status.py
TimeoutStartSec=15
EOF
cat > /etc/systemd/system/pi-codex-network-status.timer <<'EOF'
[Unit]
Description=Update dashboard network telemetry
[Timer]
OnBootSec=5s
OnUnitActiveSec=15s
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/codex-daemon.service <<'EOF'
[Unit]
Description=Codex managed app-server daemon
After=network-online.target wg-quick@ivpn-openai.service
Wants=network-online.target wg-quick@ivpn-openai.service
[Service]
Type=oneshot
RemainAfterExit=yes
User=gareth
Environment=HOME=/home/gareth
Environment=PATH=/home/gareth/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/gareth/.local/bin/codex app-server daemon start
ExecStop=/home/gareth/.local/bin/codex app-server daemon stop
TimeoutStartSec=45
TimeoutStopSec=30
[Install]
WantedBy=multi-user.target
EOF
systemd-analyze verify /etc/systemd/system/codex-daemon.service /etc/systemd/system/pi-codex-routes.service /etc/systemd/system/pi-codex-network-status.service
systemctl daemon-reload
systemctl enable --now pi-codex-routes.timer pi-codex-network-status.timer
systemctl start pi-codex-network-status.service
systemctl enable codex-daemon.service
