import subprocess,json,time
from pathlib import Path
hosts=json.loads(Path('/tmp/pi-ivpn-hosts.json').read_text())
c=json.loads(Path('/home/gareth/.config/pi-network/wireguard-public-config.json').read_text())
for host in sorted(hosts,key=lambda h:('sg1' not in h['hostname'],h['hostname'])):
    old=subprocess.check_output(['wg','show','ivpn-openai','peers'],text=True).strip()
    if old:subprocess.run(['wg','set','ivpn-openai','peer',old,'remove'],check=True)
    subprocess.run(['wg','set','ivpn-openai','peer',host['public_key'],'endpoint',host['host']+':443','allowed-ips',','.join(c['allowed_ips']),'persistent-keepalive','25'],check=True)
    probe=subprocess.run(['curl','-4','-sS','--resolve','api.openai.com:443:162.159.140.245','-I','--connect-timeout','8','--max-time','12','https://api.openai.com/v1/models'],capture_output=True,text=True)
    handshake=subprocess.check_output(['wg','show','ivpn-openai','latest-handshakes'],text=True).strip()
    print(json.dumps({'host':host['hostname'],'curl_exit':probe.returncode,'http':probe.stdout.splitlines()[:1],'handshake':handshake}),flush=True)
    if probe.returncode==0:
        c['endpoint']=host['host']+':443';c['public_key']=host['public_key']
        Path('/home/gareth/.config/pi-network/wireguard-public-config.json').write_text(json.dumps(c,indent=2))
        p=Path('/etc/wireguard/ivpn-openai.conf');s=p.read_text();import re
        s=re.sub(r'^PublicKey = .*$', 'PublicKey = '+c['public_key'],s,flags=re.M);s=re.sub(r'^Endpoint = .*$', 'Endpoint = '+c['endpoint'],s,flags=re.M);p.write_text(s)
        print('Working peer saved',flush=True);break
