"""Linux read-only dashboard telemetry and fixed 400x300 monochrome renderer."""
from collections import deque
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re
import shutil
import subprocess
import time
from PIL import Image, ImageDraw, ImageFont


def cpu_counters(text):
    result={}
    for line in text.splitlines():
        fields=line.split()
        if fields and re.fullmatch(r'cpu\d+',fields[0]):
            values=list(map(int,fields[1:9]))  # guest times already included in user/nice
            result[fields[0]]=(sum(values),sum(values[3:5]))
    return result


def net_counters(text):
    result={}
    for line in text.splitlines():
        if ':' not in line:continue
        name,values=line.split(':',1);name=name.strip();v=values.split()
        if name!='lo' and len(v)>=16:result[name]=(int(v[0]),int(v[8]))
    return result


def disk_counters(text,name):
    for line in text.splitlines():
        v=line.split()
        if len(v)>=14 and v[2]==name:return (int(v[5])*512,int(v[9])*512)
    return None


def counter_rates(old,new,seconds):
    if old is None or new is None or seconds<=0:return None
    if any(b<a for a,b in zip(old,new)):return None  # reset: no fictitious spike
    return [(b-a)/seconds for a,b in zip(old,new)]


def ip_addresses(records):
    result=[]
    for interface in records:
        name=interface.get('ifname','')
        if name=='lo':continue
        for address in interface.get('addr_info',[]):
            if address.get('family') in ('inet','inet6') and address.get('local'):
                result.append({'interface':name,'address':address['local'],
                               'family':address['family'],'scope':address.get('scope')})
    return sorted(result,key=lambda a:(a['interface'],a['family']!='inet',a['address']))


class NetworkMinute:
    """Rolling measured byte-rate intervals, clipped to the preceding 60 seconds."""
    def __init__(self):self.previous=None;self.intervals=deque(maxlen=121)
    def sample(self,now,counters):
        if self.previous:
            last,old=self.previous
            self.intervals.append((last,now,{name:counter_rates(old.get(name),value,now-last) for name,value in counters.items()}))
        self.previous=(now,dict(counters))
        while self.intervals and self.intervals[0][1]<=now-60:self.intervals.popleft()
        duration=sum(end-max(start,now-60) for start,end,_ in self.intervals)
        rates={}
        for name in counters:
            segments=[(end-max(start,now-60),values.get(name)) for start,end,values in self.intervals]
            if not duration or any(value is None for _,value in segments):rates[name]=[None,None]
            else:rates[name]=[sum(weight*value[i] for weight,value in segments)/duration*60 for i in range(2)]
        return rates,duration


class LinuxResources:
    def __init__(self):
        self.previous=None;self.throttled=None;self.throttle_checked=-100
        self.minute=NetworkMinute();self.addresses=None;self.address_checked=-100
        device=os.stat('/').st_dev
        path=Path(f'/sys/dev/block/{os.major(device)}:{os.minor(device)}').resolve()
        self.disk=path.parent.name if (path/'partition').exists() else path.name

    @staticmethod
    def read(path):
        try:return Path(path).read_text()
        except OSError:return None

    def sample(self):
        now=time.monotonic();cpu=cpu_counters(self.read('/proc/stat') or '')
        net=net_counters(self.read('/proc/net/dev') or '')
        minute,minute_seconds=self.minute.sample(now,net)
        if now-self.address_checked>=10:
            self.address_checked=now
            try:
                output=subprocess.run(["ip","-j","address","show"],capture_output=True,text=True,timeout=1,check=True).stdout
                self.addresses=ip_addresses(json.loads(output))
            except (OSError,ValueError,subprocess.SubprocessError):self.addresses=None
        disk=disk_counters(self.read('/proc/diskstats') or '',self.disk)
        cores={};network={};disk_rate=None
        if self.previous:
            last,old_cpu,old_net,old_disk=self.previous;seconds=now-last
            for name,value in cpu.items():
                rates=counter_rates(old_cpu.get(name),value,seconds)
                cores[name]=100*(1-rates[1]/rates[0]) if rates and rates[0]>0 else None
            for name,value in net.items():network[name]=counter_rates(old_net.get(name),value,seconds)
            disk_rate=counter_rates(old_disk,disk,seconds)
        self.previous=(now,cpu,net,disk)
        temperature=self.read('/sys/class/thermal/thermal_zone0/temp')
        uptime=self.read('/proc/uptime')
        wifi={}
        for line in (self.read('/proc/net/wireless') or '').splitlines():
            if ':' in line:
                name,values=line.split(':',1);v=values.split()
                if len(v)>=3:wifi[name.strip()]=float(v[2].rstrip('.'))
        if now-self.throttle_checked>=10:
            self.throttle_checked=now
            try:
                text=subprocess.run(['vcgencmd','get_throttled'],capture_output=True,text=True,timeout=1,check=True).stdout
                self.throttled=int(text.strip().split('=')[1],16)
            except (OSError,ValueError,IndexError,subprocess.SubprocessError):self.throttled=None
        usage=shutil.disk_usage('/')
        return {'addresses':self.addresses,'network_per_minute':minute,'network_window_seconds':minute_seconds,'network_since_boot':net,'cores':cores,'network':network,'disk_rates':disk_rate,'disk_device':self.disk,
                'temperature_c':float(temperature)/1000 if temperature else None,
                'uptime_seconds':float(uptime.split()[0]) if uptime else None,
                'disk_free_bytes':usage.free,'disk_total_bytes':usage.total,'wifi_dbm':wifi,'throttled':self.throttled}


def average_resources(samples):
    """Missing/reset intervals remain unavailable, never silently reported zero."""
    latest=samples[-1][1]['resources'];result=dict(latest)
    def weighted(getter):
        values=[(weight,getter(s.get('resources',{}))) for weight,s in samples]
        if any(v is None for _,v in values):return None
        return sum(w*v for w,v in values)/sum(w for w,_ in values)
    result['cores']={name:weighted(lambda r:r.get('cores',{}).get(name)) for name in latest['cores']}
    result['network']={name:[weighted(lambda r,i=i:r.get('network',{}).get(name)[i] if r.get('network',{}).get(name) is not None else None) for i in range(2)] for name in latest['network']}
    result['disk_rates']=[weighted(lambda r,i=i:r['disk_rates'][i] if r.get('disk_rates') is not None else None) for i in range(2)]
    return result


class Dashboard:
    def __init__(self):self.history=deque(maxlen=31)
    def render(self,summary,sequence,received,font_path=None):
        cpu=max(0,min(100,100-summary['cpu']['id']-summary['cpu']['wa']));mem=summary['memory'];percent=100*mem['used']/mem['total'] if mem['total'] else 0
        self.history.append((received,cpu,percent))
        while self.history and received-self.history[0][0]>300:self.history.popleft()
        r=summary.get('resources',{});image=Image.new('1',(400,300),1);d=ImageDraw.Draw(image)
        paths=[font_path] if font_path else ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/System/Library/Fonts/Supplemental/Arial.ttf']
        path=next((p for p in paths if p and Path(p).exists()),None)
        def font(size):return ImageFont.truetype(path,size) if path else ImageFont.load_default(size=size)
        small=font(11);normal=font(12);big=font(25);title=font(14)
        def text(x,y,value,f=normal):d.text((x,y),str(value),font=f,fill=0)
        def bar(x,y,w,p):
            d.rectangle((x,y,x+w,y+6),outline=0)
            if p is not None:d.rectangle((x+1,y+1,x+max(1,int((w-2)*max(0,min(100,p))/100)),y+5),fill=0)
        def rate(value):
            if value is None:return '--'
            return f'{value/1073741824:.1f}G' if value>=1073741824 else f'{value/1048576:.1f}M' if value>=1048576 else f'{value/1024:.1f}K'
        text(7,3,'RASPBERRY PI',title);text(237,5,datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%H:%M:%S +08:00'),small)
        d.line((0,24,399,24),fill=0);d.line((199,25,199,112),fill=0)
        text(7,29,'CPU / 10s AVG',small);text(7,42,f'{cpu:.0f}%',big)
        temp=r.get('temperature_c');text(106,52,f'{temp:.1f} C' if temp is not None else '-- C')
        cores=sorted(r.get('cores',{}).items())[:4]
        for i in range(4):
            value=cores[i][1] if i<len(cores) else None;x=7+i*48
            text(x,77,f'C{i} {value:.0f}%' if value is not None else f'C{i} --',small);bar(x,94,40,value)
        text(208,29,'RAM / 10s AVG',small);text(208,43,f'{mem["used"]/1024:.1f}/{mem["total"]/1024:.1f} GiB',font(19));bar(209,71,181,percent)
        free=r.get('disk_free_bytes');free_text=f'{free/1073741824:.1f}G' if free is not None else '--'
        text(208,84,f'Swap {summary["swap_used_mib"]:.0f}M / Free {free_text}',small)
        disk=r.get('disk_rates') or [None,None]
        text(208,99,f'Disk R/W {rate(disk[0])}/{rate(disk[1])}B/s',small)
        d.line((0,115,399,115),fill=0)
        def spark(x,label,index):
            text(x,119,label,small);text(x+139,119,'0-100%',small)
            d.rectangle((x,136,x+182,169),outline=0)
            points=[(x+1+int(180*(1-(received-t)/300)),168-int(31*v/100)) for t,*vals in self.history for v in [vals[index]]]
            if len(points)>1:d.line(points,fill=0,width=1)
            elif points:d.point(points[0],fill=0)
        spark(7,'CPU / last 5 min',0);spark(209,'RAM / last 5 min',1)
        d.line((0,176,399,176),fill=0)
        addresses=r.get('addresses') or []
        page=((sequence-1)//3)%max(1,(len(addresses)+1)//2)
        visible=addresses[page*2:page*2+2]
        for i in range(2):
            if i<len(visible):
                a=visible[i];label=f'{a["interface"]}  {a["address"]}'
            else:label='IP unavailable' if not addresses and r.get('addresses') is None else 'No additional IP'
            f=small
            if d.textlength(label,font=f)>386:f=font(9)
            text(7,179+i*14,label,f)
        d.line((0,209,399,209),fill=0);d.line((199,210,199,275),fill=0)
        networks=r.get('network_per_minute',{})
        iface=visible[0]['interface'] if visible else 'wlan0' if 'wlan0' in networks else next(iter(networks),None)
        window=r.get('network_window_seconds',0)
        text(7,213,f'{iface or "NET"} / {min(60,round(window))}s AVG',small)
        speeds=networks.get(iface,[None,None]);totals=r.get('network_since_boot',{}).get(iface,[None,None])
        text(7,228,f'RX {rate(speeds[0])}B/min',small);text(7,240,f'TX {rate(speeds[1])}B/min',small)
        text(7,252,f'Boot RX {rate(totals[0])}B',small);text(7,264,f'     TX {rate(totals[1])}B',small)
        text(207,213,'BUSIEST / CPU% / MiB',small)
        for i,p in enumerate(summary['processes'][:3]):
            name=p['command'][:13]
            text(207,230+i*14,f'{name:13} {p["cpu"]:4.1f} {p["rss_mib"]:.0f}',small)
        d.line((0,276,399,276),fill=0)
        up=r.get('uptime_seconds');uptime=f'{int(up//86400)}d {int(up%86400//3600)}h' if up is not None else '--'
        wifi=r.get('wifi_dbm',{}).get('wlan0');status=r.get('throttled')
        health='Flags --' if status is None else 'WARN '+hex(status) if status else 'Flags OK'
        text(7,282,f'Up {uptime} | WiFi {wifi:.0f} dBm' if wifi is not None else f'Up {uptime} | WiFi --',small);text(250,282,f'{health}  #{sequence}',small)
        return image
