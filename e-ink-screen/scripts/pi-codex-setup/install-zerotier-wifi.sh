#!/bin/sh
set -eu
test "$(id -u)" = 0
install -m 0755 /tmp/zerotier-wifi.py /usr/local/lib/pi-codex/zerotier-wifi.py
python3 - <<'PY'
from pathlib import Path
import json,shutil
p=Path('/var/lib/zerotier-one/local.conf')
if p.exists():
    backup=p.with_name('local.conf.before-wifi-only')
    if not backup.exists():shutil.copy2(p,backup)
    value=json.loads(p.read_text())
else:value={}
settings=value.setdefault('settings',{})
blacklist=settings.get('interfacePrefixBlacklist',[])
settings['interfacePrefixBlacklist']=list(dict.fromkeys(blacklist+['ivpn-openai','wg','tun','tap','utun','zt']))
p.write_text(json.dumps(value,indent=2)+'\n');p.chmod(0o600)
PY
install -d -m 0755 /etc/systemd/system/zerotier-one.service.d
cat > /etc/systemd/system/zerotier-one.service.d/wifi-only.conf <<'EOF'
[Unit]
After=NetworkManager.service
[Service]
ExecStartPre=/usr/local/lib/pi-codex/zerotier-wifi.py
EOF
cat > /etc/NetworkManager/dispatcher.d/90-zerotier-wifi <<'EOF'
#!/bin/sh
case "$1:$2" in
 wlan0:up|wlan0:down|wlan0:dhcp4-change|wlan0:dhcp6-change|wlan0:reapply)
  /usr/local/lib/pi-codex/zerotier-wifi.py --routes-only
  ;;
esac
EOF
chmod 0755 /etc/NetworkManager/dispatcher.d/90-zerotier-wifi
/usr/local/lib/pi-codex/zerotier-wifi.py
systemctl daemon-reload
systemctl restart zerotier-one.service
