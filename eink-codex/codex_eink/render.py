"""Monochrome 400x300 agent and usage screen. No GPIO/network access."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from .usage import window_view,credit_page


def render(snapshot):
    image=Image.new('1',(400,300),1);draw=ImageDraw.Draw(image)
    font_path=next((p for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/System/Library/Fonts/Supplemental/Arial.ttf') if Path(p).exists()),None)
    def text(x,y,value,size=12,fill=0):
        font=ImageFont.truetype(font_path,size) if font_path else ImageFont.load_default(size=size)
        draw.text((x,y),str(value),font=font,fill=fill)
    fleet='fleet_counts' in snapshot
    counts=(snapshot.get('fleet_counts') if fleet else snapshot.get('counts')) or {}
    known=bool(counts) if fleet else snapshot.get('available')
    partial=fleet and not snapshot.get('fleet_complete')
    for x,key,label in ((8,'active','ACTIVE'),(108,'waiting','WAITING'),(208,'idle','IDLE'),(308,'errors','ERRORS')):
        value=counts.get(key,'--') if known else '--'
        text(x,3,value,30);text(x,39,label+('*' if partial else ''),11)
    hosts=snapshot.get('hosts') or {'pi':{'label':'Pi','state':'LIVE' if snapshot.get('available') else 'OFFLINE','counts':snapshot.get('counts')}}
    text(8,59,'MACHINE',10);text(143,59,'ACTIVE',10);text(203,59,'WAIT',10);text(259,59,'IDLE',10);text(319,59,'STATUS',10)
    for i,host in enumerate(list(hosts.values())[:3]):
        y=79+i*20
        text(8,y,host['label'],12)
        values=host.get('counts') or {}
        for x,key in ((143,'active'),(203,'waiting'),(259,'idle')):
            text(x,y,values.get(key,'--') if host['state']=='LIVE' else '--',11)
        text(319,y,host['state'],10)
    def window(y,title,duration):
        view=window_view(snapshot,duration)
        draw.rectangle((8,y,391,y+51),outline=0)
        text(16,y+4,title,11)
        left=view['remaining']
        text(272,y+3,f'{left:g}% left' if left is not None else 'unavailable',14)
        draw.rectangle((16,y+29,183,y+39),outline=0)
        if left is not None and left>0:
            draw.rectangle((16,y+29,16+round(167*left/100),y+39),fill=0)
        if left is None:text(87,y+26,'--',11)
        prefix='Reset in ' if view['reset'] not in ('unavailable','Due / awaiting API') else 'Reset: '
        text(197,y+27,prefix+view['reset'],10)
    recovery=snapshot.get('auth_recovery')
    window(143,'7-DAY WINDOW',10080)
    extra=credit_page(snapshot)
    count=extra['available']
    title='EXTRA RESETS: '+(str(count) if count is not None else 'unavailable')
    if extra['pages']>1:title+=f"  ({extra['page']}/{extra['pages']})"
    text(8,202,title,13)
    for i,row in enumerate(extra['rows']):
        label='expires in '+row['expires'] if row['expires'] not in ('unavailable','EXPIRED') else 'expiry '+row['expires']
        text(16,223+i*17,f"Reset {row['index']} {label}",12)
    if not extra['rows']:
        text(16,224,'No extra resets available' if count==0 else 'Expiry details unavailable',12)
    if recovery:
        draw.rectangle((0,140,399,280),fill=1)
        text(8,143,'CODEX LOGIN REQUIRED',17)
        if recovery.get('code'):
            text(8,170,'Open on phone or computer:',12)
            text(8,190,'auth.openai.com/codex/device',18)
            text(8,214,recovery['code'],30)
            text(8,254,f"Enter code | expires in {recovery['expires_in_minutes']}m",12)
        else:
            message={'starting':'Requesting login code...',
                     'retry':'Login failed/expired. Retrying shortly.',
                     'reload_pending':'Signed in. Waiting for Pi agents to finish.',
                     'reload_retry':'Signed in. Codex reload will retry shortly.',
                     'reloading':'Signed in. Reloading Codex...'}.get(recovery['state'],'Requesting login code...')
            text(8,179,message,12)
    network=snapshot.get('network',{})
    if network.get('stale',True):status='Network status unavailable'
    else:
        stamp=network.get('wireguard',{}).get('latest_handshake',0)
        age=max(0,int((snapshot['time']-stamp)//60)) if stamp else None
        vpn=f'WG age {age}m' if age is not None else 'WG no handshake'
        status=f"{vpn} | ZT {network.get('zerotier',{}).get('status','UNKNOWN')}"
    draw.line((8,282,391,282),fill=0)
    health=(f"* PARTIAL {snapshot['fleet_fresh']}/{snapshot['fleet_host_count']} hosts" if partial else 'ALL HOSTS LIVE') if fleet else ('LIVE' if snapshot.get('available') else 'DAEMON UNAVAILABLE')
    if any(error.startswith('Quota:') for error in snapshot.get('errors',[])):health='USAGE UNAVAILABLE'
    clock=datetime.fromtimestamp(snapshot['time'],ZoneInfo('Asia/Shanghai')).strftime('%H:%M')+' +08'
    text(8,287,f'{health} | {status} | {clock}',9)
    return image
