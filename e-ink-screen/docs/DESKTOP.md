# Display a Pi desktop snapshot

The `desktop` command captures the active Wayland desktop with `grim`, scales
the whole screenshot without cropping or changing its aspect ratio, converts
it to monochrome and performs exactly one full e-paper update. It does not
change HDMI resolution or continuously mirror the desktop.

On this Pi, the desktop is labwc/Wayland, running as `gareth`. `grim` was already
installed. On a new Pi with a compatible Wayland compositor:

```sh
sudo apt-get install --no-install-recommends -y grim
```

Run as the same account that owns the desktop session. The command reads its
user service environment for `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR`. No root
access is needed for capture or display after SPI/GPIO setup. If no compatible
Wayland desktop is active, provide an existing screenshot with `--image`.

From the source directory, after the normal powered-off inspection and 3 Ω
selector confirmation, in tmux:

```sh
python3 -m hink_diag desktop --hardware --resistor 3 --spacing 0 --inspection config/inspection.json --runs runs
```

Default transport is the proven conservative mode 0 / MSB-first / 100 kHz.
The command saves the original screenshot as `source-desktop.png` and expected
400 × 300 image as `patterns/desktop.png`, plus the two 7,500-byte controller
streams and full 15,000-byte framebuffer. A 20-pixel footer carries the unique
run ID; remaining space contains the whole desktop with white letterboxing as
needed. Default conversion uses Floyd–Steinberg dithering; `--dither threshold`
uses plain black/white thresholding. Text shrinks with a large source desktop.

For a supplied image, preview without touching GPIO/SPI:

```sh
python3 -m hink_diag desktop --image screenshot.png --runs runs
python3 -m hink_diag desktop --mock --image screenshot.png --runs runs
```

Dry-run/mock never implicitly captures the live desktop. For actual display of
that supplied screenshot, add `--hardware --inspection config/inspection.json`.
`--rotation 90`, `180` or `270` rotates the logical image before packing without
changing the physical framebuffer dimensions.

After the single update, normal booster-off/sleep and GPIO/SPI cleanup run.
Bounded BUSY waits, deadline, interruption handling and no automatic retries
are the same as the diagnostic suite. Verify the new footer, whole image and
both halves against the saved PNG; host completion alone remains INCONCLUSIVE.
To annotate a verified result, use the normal observation schema with the step
name `desktop`. Retention is not required for this snapshot-specific result.

The display remains a static snapshot until another explicit command refreshes
it. Keep the physical 3 Ω setting and fan wiring unchanged.

## Executed snapshot

Run `20261008-003355-fa3b45`, 2026-10-08 00:33:55 UTC+08:00 captured the live
1680 × 1050 desktop and fitted it to 400 × 250 within the 400 × 300 framebuffer.
One update completed without errors; BUSY 1.598 s, normal final sleep. Whole-screen
image and no heat/supply trouble confirmed by user: **PASS**. Desktop resolution remained unchanged.
[Expected PNG](../runs/20261008-003355-fa3b45/patterns/desktop.png) ·
[Original screenshot](../runs/20261008-003355-fa3b45/source-desktop.png) ·
[Raw result](../runs/20261008-003355-fa3b45/result.json).
The updated software passed 46 tests on host and Pi.
