"""400x300 row-major monochrome; row-wise 200x300 controller planes."""
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 400, 300
PATTERNS = ("white", "black", "halves", "halves-swapped", "diagnostic", "wake")


def pattern(name, run_id, rotation=0):
    if name not in PATTERNS and name != "smoke":
        raise ValueError(f"Unknown pattern: {name}")
    # Logical canvas changes for 90-degree rotations; physical framebuffer stays 400x300.
    size = (HEIGHT, WIDTH) if rotation in (90, 270) else (WIDTH, HEIGHT)
    im = Image.new("1", size, 0 if name == "black" else 1)
    d = ImageDraw.Draw(im)
    w, h = size
    if name in ("halves", "halves-swapped"):
        # Halves always exercise the physical x=200 seam regardless of text rotation.
        im = Image.new("1", (WIDTH, HEIGHT), 1)
        d = ImageDraw.Draw(im)
        left = 0 if name == "halves" else 200
        d.rectangle((left, 0, left + 199, HEIGHT - 1), fill=0)
        return im
    if name in ("white", "black"):
        return im.rotate(-rotation, expand=True)
    d.rectangle((0, 0, w - 1, h - 1), outline=0, width=3)
    font = ImageFont.load_default(size=14)
    for label, xy in (("TL", (8, 8)), ("TR", (w-35, 8)),
                      ("BL", (8, h-25)), ("BR", (w-35, h-25))):
        d.text(xy, label, font=font, fill=0)
    d.text((15, 38), "HINK-E042A03-A1", font=font, fill=0)
    d.text((15, 60), run_id, font=font, fill=0)
    d.text((15, 82), name.upper(), font=font, fill=0)
    d.line((10, 110, w-11, h-40), fill=0, width=3)
    d.line((10, h-40, w-11, 110), fill=0, width=1)
    for y in range(120, min(216, h-30), 12):
        for x in range(w//2-72, w//2+72, 12):
            if ((x-(w//2-72))//12 + (y-120)//12) % 2 == 0:
                d.rectangle((x, y, x+11, y+11), fill=0)
    d.ellipse((w//2-35, h-70, w//2+35, h-15), outline=0, width=2)
    return im.rotate(-rotation, expand=True)


def pack(image):
    if image.size != (WIDTH, HEIGHT):
        raise ValueError("Physical image must be 400x300")
    frame = image.convert("1", dither=Image.Dither.NONE).tobytes()
    if len(frame) != 15_000:
        raise ValueError("Expected 15000 framebuffer bytes")
    return frame


def split_rows(frame):
    if len(frame) != 15_000:
        raise ValueError("Expected 15000 framebuffer bytes")
    # Each row has 50 bytes. Never split into two contiguous 7500-byte chunks.
    return tuple(b"".join(frame[y*50+offset:y*50+offset+25] for y in range(300))
                 for offset in (0, 25))


def reconstruct(left, right):
    if len(left) != 7500 or len(right) != 7500:
        raise ValueError("Each controller requires 7500 bytes")
    frame = b"".join(left[y*25:(y+1)*25]+right[y*25:(y+1)*25] for y in range(300))
    return Image.frombytes("1", (WIDTH, HEIGHT), frame)
