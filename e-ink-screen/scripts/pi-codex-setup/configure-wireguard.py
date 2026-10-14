#!/usr/bin/env python3
import json,os,subprocess
from pathlib import Path
os.umask(0o077)
root=Path('/home/gareth/.config/pi-network')
c=json.loads((root/'wireguard-public-config.json').read_text());key=(root/'wireguard.key').read_text().strip()
config=f'[Interface]\nPrivateKey = {key}\nAddress = {c["address"]}\nMTU = 1380\n\n[Peer]\nPublicKey = {c["public_key"]}\nEndpoint = {c["endpoint"]}\nAllowedIPs = {", ".join(c["allowed_ips"])}\nPersistentKeepalive = 25\n'
path=Path('/etc/wireguard/ivpn-openai.conf');path.parent.mkdir(exist_ok=True);path.write_text(config);path.chmod(0o600)
subprocess.run(['systemctl','enable','--now','wg-quick@ivpn-openai'],check=True)
subprocess.run(['wg','show','ivpn-openai'],check=True)
