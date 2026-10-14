"""Pure usage normalization/countdowns. No account actions or reset redemption."""
import math


def number(value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value<minimum:
        raise ValueError('Invalid usage number')
    return value


def normalize(response):
    """Persist only displayed fields; window duration identifies 5h/7d, not API slot."""
    limits=response.get('rateLimits') or {}
    windows=[]
    for name in ('primary','secondary'):
        window=limits.get(name)
        if window:
            used=number(window['usedPercent'])
            duration=number(window['windowDurationMins'],1)
            reset=window.get('resetsAt')
            if reset is not None:reset=number(reset)
            windows.append({'usedPercent':used,'windowDurationMins':duration,'resetsAt':reset})
    extra=response.get('rateLimitResetCredits')
    available=None;credits=[]
    if isinstance(extra,dict):
        value=extra.get('availableCount')
        if value is not None:
            number(value)
            if not isinstance(value,int):raise ValueError('Reset count must be integer')
            available=value
        for credit in extra.get('credits') or []:
            if credit.get('status')!='available':continue
            expires=credit.get('expiresAt')
            if expires is not None:expires=number(expires)
            credits.append({'expiresAt':expires})
        credits.sort(key=lambda c:c['expiresAt'] if c['expiresAt'] is not None else float('inf'))
    return windows, {'availableCount':available,'credits':credits}


def countdown(timestamp, now, expired='Due / awaiting API'):
    if timestamp is None:return 'unavailable'
    seconds=number(timestamp)-number(now)
    if seconds<=0:return expired
    minutes=math.ceil(seconds/60)
    days,remainder=divmod(minutes,1440)
    hours,minutes=divmod(remainder,60)
    if days:return f'{days}d {hours}h {minutes}m'
    if hours:return f'{hours}h {minutes}m'
    return f'{minutes}m'


def window_view(snapshot, duration):
    matches=[w for w in snapshot.get('quota',[]) if w.get('windowDurationMins')==duration]
    if len(matches)!=1:return {'remaining':None,'reset':'unavailable'}
    window=matches[0]
    return {'remaining':max(0,100-number(window['usedPercent'])),
            'reset':countdown(window.get('resetsAt'),snapshot['time'])}


def credit_page(snapshot):
    extra=snapshot.get('extra_resets') or {}
    credits=extra.get('credits') or []
    pages=max(1,math.ceil(len(credits)/3))
    page=int(snapshot['time']//60)%pages
    rows=[{'index':i+1,'expires':countdown(c.get('expiresAt'),snapshot['time'],'EXPIRED')}
          for i,c in enumerate(credits) if page*3<=i<(page+1)*3]
    return {'available':extra.get('availableCount'),'rows':rows,'page':page+1,'pages':pages}
