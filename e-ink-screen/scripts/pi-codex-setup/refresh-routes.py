#!/usr/bin/env python3
"""Refresh selected /32 destinations using HTTPS DNS; preserve normal routes/DNS."""
import ipaddress,json,re,subprocess,urllib.request
from pathlib import Path
root=Path('/home/gareth/.config/pi-network');path=root/'wireguard-public-config.json';c=json.loads(path.read_text())
resolved={};allowed=set(c['allowed_ips'])
for name in c['domains']:
    request=urllib.request.Request('https://cloudflare-dns.com/dns-query?name='+name+'&type=A',headers={'Accept':'application/dns-json'})
    try:
        with urllib.request.urlopen(request,timeout=6) as r:result=json.load(r)
        values=sorted({str(ipaddress.IPv4Address(item['data'])) for item in result.get('Answer',[]) if item['type']==1})
        if values:resolved[name]=values;allowed.update(ip+'/32' for ip in values)
    except Exception:pass
if not all(name in resolved for name in ('chatgpt.com','auth.openai.com','api.openai.com')):
    raise SystemExit('Required domain resolution failed; existing host mappings/routes preserved')
for route in allowed:
    network=ipaddress.ip_network(route);assert network.version==4 and network.prefixlen==32
# Apply routing before hosts, so newly mapped destinations never bypass tunnel.
subprocess.run(['wg','set','ivpn-openai','peer',c['public_key'],'allowed-ips',','.join(sorted(allowed))],check=True)
for route in sorted(allowed):subprocess.run(['ip','route','replace',route,'dev','ivpn-openai'],check=True)
p=Path('/etc/wireguard/ivpn-openai.conf');p.write_text(re.sub(r'^AllowedIPs = .*$', 'AllowedIPs = '+', '.join(sorted(allowed)),p.read_text(),flags=re.M))
hosts=Path('/etc/hosts');old=hosts.read_text();begin='# BEGIN PI CODEX OPENAI';end='# END PI CODEX OPENAI'
old=re.sub(re.escape(begin)+r'.*?'+re.escape(end)+r'\n?', '',old,flags=re.S)
block=begin+'\n'+''.join(ip+' '+name+'\n' for name,ips in resolved.items() for ip in ips)+end+'\n'
hosts.write_text(old.rstrip()+'\n'+block)
c['resolved_ipv4']=resolved;c['allowed_ips']=sorted(allowed);path.write_text(json.dumps(c,indent=2)+'\n')
print(json.dumps({'selected_routes':len(allowed),'domains_resolved':list(resolved),'default_route_unchanged':True}))
