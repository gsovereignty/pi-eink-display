# Detailed operating guide

Exact dual-controller driver, bounded CLI, mocks, and evidence archive. This
workspace was empty on arrival. No arbitrary Waveshare panel driver is used.
Implementation derives from xljxlj's `GxEPD2_2IC_420_A03`, modified library 1.4.8;
source and hashes in [evidence/SOURCES.md](../evidence/SOURCES.md).

**A software PASS is not a hardware PASS.** Whole new image, correct orientation,
both halves and intended sequence must be observed. No MISO means no generic
device-ID/panel-presence read. BUSY does not validate both controllers.

## Wiring and physical inspection

BCM numbers belong in software; header numbers locate wires. SDA means MOSI.

| Adapter | BCM / function | Header |
|---|---|---|
| 3V3 | 3.3 V | 1 |
| GND | Ground | 14 |
| SDA | 10 / MOSI | 19 |
| SCK | 11 / clock | 23 |
| RST | 17 | 11 |
| DC | 25 | 22 |
| CS1 | 8 | 24 |
| CS2 | 7 | 26 |
| BUSY | 24, strictly input | 18 |

1. Shut Pi down normally. Disconnect **every** supply that can energize Pi or
   adapter, including USB/back-feed sources. GPIO release does not remove power.
2. Allow discharge; if measuring, confirm supply has fallen to zero. Never
   measure resistance/continuity on powered hardware.
3. Inspect listed connections, no adjacent-pin shorts, ribbon latch/seating,
   exposed-contact direction, folds/tears/corrosion. Do not disturb fan wiring.
   Do not disconnect ribbon during refresh.
4. Set physical switch to **3 Ω** and explicitly confirm it. CLI cannot change
   or verify selector. Reconnect power only after inspection.
5. Copy `config/inspection.example.json` to `config/inspection.json`. Replace
   observer/timestamp, set confirmed facts to `true`, record ambient description,
   starting retained image and available instruments. Nulls never count as PASS.
   Do not fill facts you have not checked. A fresh inspection is needed after
   wiring/selector changes; do not reuse another setting's confirmation.

## Install and enable SPI on Pi

SSH account `gareth`, Bonjour `raspberrypi.local`; IPv4 last observed
`192.168.50.191`. Dedicated persistent socket `~/.ssh/raspberrypi`.

```sh
ssh -MNf -o ControlMaster=auto -o ControlPersist=yes -S "$HOME/.ssh/raspberrypi" gareth@raspberrypi.local
ssh -S "$HOME/.ssh/raspberrypi" gareth@raspberrypi.local 'hostname'
```

Pi working copy: `/home/gareth/git/hardware/e-ink-screen`. Run there:

```sh
sudo sh scripts/setup_pi.sh
sudo reboot
```

Setup saves boot-config backup, adds `[all]` / `dtoverlay=spi0-0cs,no_miso`,
and installs Debian packages `python3-lgpio python3-spidev python3-pil gpiod tmux`.
Keep `dtparam=spi=on` and conflicting SPI-CS overlays disabled. `no_miso` also
preserves unused GPIO9. Existing audio/display/fan configuration is left intact.
Read-only preflight and actual exclusive GPIO claims must prove GPIO7/8 free;
setting `spidev.no_cs` alone cannot free kernel-owned lines. If this overlay/kernel
still claims either select, stop and inspect live device tree rather than moving
CS onto unknown fan connections.

Debian system Python already has dependencies on this Pi. No pip installation
needed. Other machines: `python3 -m pip install -e .`; on Pi a venv with
`--system-site-packages` can reuse distro GPIO libraries. Versions live in run
inventory; tested local Pillow 12.3.0 and Pi Pillow 11.1.0.

Temporary sudo rule, if enabled, can be removed with
`sudo rm /etc/sudoers.d/90-epaper-diagnostics` after setup. Do not place passwords
in source, command history, configuration or logs.

## Software validation and safe preflight

```sh
python3 -m unittest discover -v
python3 scripts/reference_oracle.py
python3 -m hink_diag functional --runs runs
python3 -m hink_diag smoke --mock --runs runs
python3 -m hink_diag functional --mock --runs runs
python3 -m hink_diag functional --mock --resistor 0.47 --runs runs
python3 -m hink_diag preflight --hardware --runs runs
python3 -m hink_diag preflight --hardware --sample-busy --runs runs
```

Default is **dry-run**: generates PNGs and buffers, opens no transport, sends no
refresh. Mock uses virtual time/GPIO/SPI and logs simulated commands; hardware
comparison excludes mock results. Preflight is read-only even with `--hardware`:
model, kernel, Python/libs, permissions, GPIO names/consumers, pinctrl and SPI
devices. It does not reset panel or enable booster. Expected preflight failure
before SPI setup is a Pi configuration finding, not evidence of board failure.
Optional `--sample-busy` briefly claims only GPIO24 as an input and samples it;
all other preflight GPIO access remains metadata-only. Static BUSY does not prove
panel presence or polarity.

Reference oracle compiles actual archived C++ with a recording base/Arduino
shim: verifies both 7500-byte streams and initialization/refresh/sleep trace.
Unit tests cover bit order, polarity, rotation, seam pixels, GPIO input ownership,
CS/DC timing, reset, BUSY transitions, stuck high/low, exception/interrupt cleanup,
deadline, import/dry-run safety, no refresh retries, and evidence gates.

## Optional instrument checks before booster use

No invented readings. Multimeter black lead on adapter GND/header 14; powered
DC voltage check at adapter 3V3/header 1 should be near 3.3 V. Panel VCI operating
range is 2.4–3.7 V; absolute maximum 3.7 V is not a target. Measure loaded voltage
only during an approved refresh. Stop on supply droop outside limits or heating.
No adapter-specific current limit available; panel's 12 mA datasheet figure is
not a limit for adapter input or switching peaks.

While **unpowered**, ground/header continuity and each signal path can be checked.
FPC pin 12 is panel master CS#, FPC pin 1 slave CS1#; adapter CS1/CS2 labels may
differ. Probe only safely accessible pads; do not short adjacent ribbon contacts.
No adapter schematic exists, so routing stays unverified until continuity or
images demonstrate it. Never use resistance mode while powered.

Analyzer: 3.3 V-compatible inputs, common adapter ground; probe GPIO10/header19
MOSI, GPIO11/header23 clock, GPIO17/header11 reset, GPIO25/header22 DC,
GPIO8/header24 CS1, GPIO7/header26 CS2, GPIO24/header18 BUSY. Use at least
2 MS/s for 100 kHz SPI. Decode mode 0, MSB first. Clock idle low; CS idle high.

After inspection, this optional signal exercise sends SPI only with both selects
high, then pulses each select separately without clocks. Booster is not enabled:

```sh
python3 -m hink_diag signals --hardware --inspection config/inspection.json --deadline 30 --runs runs
```

Expected capture: unselected `aa 55 00 ff` repeated four times, DC low/high,
CS1 low 50 ms then high, CS2 low 50 ms then high; reset stays high, BUSY sampled
strictly as input. During later smoke, reset is HIGH 10 ms / LOW 10 ms / HIGH
10 ms; DC=0 commands, DC=1 payload; broadcast selects for common commands,
individual selects for RAM. SPI writes only prove host transmission. Unexpected
BUSY polarity must be investigated; harness never flips it automatically.

## Hardware smoke and functional sequence

Use persistent visible tmux session `e-ink-diagnostics` on `raspberrypi`. Normal
`tmux` works after setup. Before sudo setup, extracted Debian tmux/libjemalloc
may be available via `/home/gareth/.local/bin/epaper-tmux`; use that wrapper if
`tmux` is absent.

```sh
tmux new-session -s e-ink-diagnostics -c /home/gareth/git/hardware/e-ink-screen
python3 -m hink_diag smoke --hardware --resistor 3 --inspection config/inspection.json --runs runs
```

If session already exists, inspect and attach instead of creating another. From
local Mac after normal tmux installation:

```sh
ssh -t -S "$HOME/.ssh/raspberrypi" gareth@raspberrypi.local 'tmux attach-session -t e-ink-diagnostics'
```

Smoke sends **one full refresh**, then booster-off/sleep. Expected image has
unique visible run ID, all corner labels, border, asymmetry, checkerboard and
features crossing x=200. Compare against its PNG; an old retained image is not
success. Enter observations only for what actually appeared.

Copy observations template, replace run ID, record `steps.smoke` facts and
contrast/ghosting/seam/completeness; optional photos are copied into run folder.
Measurements remain null unless measured. Record instrument and method; average
current and switching peaks are separate fields. Then:

```sh
python3 -m hink_diag annotate runs/ACTUAL_SMOKE_ID config/smoke-observations.json
python3 -m hink_diag functional --hardware --resistor 3 --inspection config/inspection.json --smoke-run runs/ACTUAL_SMOKE_ID --runs runs
```

Functional command requires same revision/config smoke PASS and interactive
terminal. Observe and answer after **each** image; unknown/failure stops remaining
sequence. Order: full white, full black, left black/right white, swapped halves,
asymmetric image, sleep then reset/wake and uniquely labeled further update.
No endurance loops, partial modes, unsupported fast refreshes or automatic retries.

Default spacing is 180 seconds after prior refresh completion, including wake.
Explicit `--spacing 0` permits a user-requested short supervised sequence without
additional delay; it is not validated lifetime or endurance guidance. Booster
off during spacing/manual checks. HINK minimum spacing unavailable; this is
conservative general e-paper guidance, explicitly documented in SOURCES.
Overall default deadline 1800 s, each BUSY wait 20 s (maximum configurable 30 s).
`Ctrl-C`/SIGTERM/deadline abort sends no further controller commands in uncertain
state, deasserts CS, closes SPI/releases GPIO. **Power remains physically connected.**
After stall/interrupt/error, disconnect adapter power and investigate; do not
immediately rerun. A Python deadline cannot physically cut power or guarantee
recovery from a wedged kernel; external supervision/manual power removal needed.

After successful final sleep, shut Pi down normally and disconnect all adapter
power. Observe final unique image retention; record disconnect and observation
in functional observations JSON, then annotate. This manual retention step is
required for complete functional hardware PASS. Do not switch resistor yet.

## Resistor comparison

```sh
python3 -m hink_diag comparison --runs runs
python3 -m hink_diag smoke --resistor 0.47 --runs runs
python3 -m hink_diag functional --mock --resistor 0.47 --runs runs
```

`--resistor` records position only. Both settings implemented for mock/dry-run;
**live 0.47 Ω blocked** without defensible adapter circuitry/component ratings
and exact-panel RESE/booster validation. SSD1608 reference is 2.2 Ω. Neither 3 Ω
nor 0.47 Ω is a confirmed equivalent. A blank 3 Ω screen never triggers switch
or voltage/LUT sweep.

If new evidence justifies 0.47 Ω, review fixed execution gate before live use.
Finish normal shutdown; disconnect **all** energizing sources, allow discharge,
change switch unpowered, explicitly confirm new position. Keep ribbon seated.
Repeat smoke before functional sequence. Match software revision, initialization,
SPI speed, rotation/CS mapping, starting image, pattern order, spacing and ambient.
Use a recorded common starting image (e.g. retained full white), not an unrecorded
prior pattern. Preparing that baseline is an additional explicitly planned full
refresh with spacing; it is not an automatic smoke retry. Current initial 3 Ω
smoke establishes function, not a matched resistor experiment.

Stop for abnormal heating, supply problems, documented voltage/temperature limits
or stalled controller. Logs/JSON/CSV record refresh duration/BUSY plus manual image
quality. `comparison.md`, `.json`, `.csv` mark PASS/FAIL/NOT RUN/INCONCLUSIVE.
Comparison validity requires observed functional PASS with matching conditions.
Missing voltage/current/temperature readings are unavailable, never zero.

## Failure isolation and saved evidence

Each `runs/<id>` contains configuration/code manifest, runtime, event timestamps
with +08:00, JSON/CSV results, expected/reconstructed PNGs, transmitted full/half
buffers, manual observations and supplied photos. Photo absence is explicit.
See [evidence/RESULTS.md](../evidence/RESULTS.md) for actually executed checks.

Investigate in evidence order, updating ranking after each discriminating test:

1. **Pi configuration/access:** absent SPI or owned CS. Fix overlay/permissions;
   repeat read-only preflight, then actual exclusive line claims.
2. **Transport:** verify analyzer clock/MOSI/DC/reset/CS at adapter, then accessible
   panel pads. Correct host writes alone do not prove connection.
3. **Wiring/ribbon/CS routing:** inspect unpowered; continuity FPC 12/1; halves and
   corner labels discriminate mapping, inversion and orientation. Preserve fan.
4. **Driver/batch compatibility:** compare captured init/LUT to pinned oracle;
   BUSY polarity contradiction and batch VCOM/LUT remain uncertainties. Obtain
   batch-matched working reference, not undocumented parameter sweeps.
5. **Adapter power circuitry:** measure input under load; if qualified, compare
   booster rails with documented circuit limits. No schematic or ratings means
   do not probe/sweep high-voltage rails blindly.
6. **Panel:** damage/age/batch-specific waveform remains possible. Known-good
   compatible adapter/panel substitution is needed to isolate either component.

Current absent SPI ranks Pi configuration first. Hardware transport, adapter
and panel functionality remain untested; no board-defect conclusion follows.
