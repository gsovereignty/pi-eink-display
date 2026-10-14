"""Read-only Wayland snapshot and aspect-preserving monochrome conversion."""
import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


def capture(destination):
    environment=dict(os.environ)
    result=subprocess.run(['systemctl','--user','show-environment'],capture_output=True,text=True,timeout=5)
    if result.returncode==0:
        for line in result.stdout.splitlines():
            key,separator,value=line.partition('=')
            if separator and key in ('XDG_RUNTIME_DIR','WAYLAND_DISPLAY'):
                environment[key]=value
    if not environment.get('WAYLAND_DISPLAY'):
        raise RuntimeError('No active Wayland desktop; supply --image with an existing screenshot')
    subprocess.run(['grim','-t','png',str(destination)],env=environment,check=True,timeout=10)
    return {'method':'grim Wayland screenshot','wayland_display':environment['WAYLAND_DISPLAY']}


def convert(source,run_id,rotation=0,dither='floyd-steinberg'):
    with Image.open(source) as image:
        image=ImageOps.exif_transpose(image).convert('RGBA')
        source_size=image.size
        white=Image.new('RGBA',image.size,'white');white.alpha_composite(image)
        grey=white.convert('L')
    size=(300,400) if rotation in (90,270) else (400,300)
    available=(size[0],size[1]-20)
    scaled=ImageOps.contain(grey,available,method=Image.Resampling.LANCZOS)
    canvas=Image.new('L',size,255)
    position=((size[0]-scaled.width)//2,(available[1]-scaled.height)//2)
    canvas.paste(scaled,position)
    draw=ImageDraw.Draw(canvas)
    draw.line((0,size[1]-20,size[0]-1,size[1]-20),fill=0)
    draw.text((4,size[1]-17),f'DESKTOP {run_id}',fill=0,font=ImageFont.load_default(size=12))
    method=Image.Dither.FLOYDSTEINBERG if dither=='floyd-steinberg' else Image.Dither.NONE
    return canvas.convert('1',dither=method).rotate(-rotation,expand=True),{
        'source_size':list(source_size),'scaled_size':list(scaled.size),'position':list(position),
        'dither':dither,'footer_pixels':20,'aspect_ratio_preserved':True,'desktop_resolution_changed':False}
