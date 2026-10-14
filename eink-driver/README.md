# eink-driver

Independent reusable driver and command-line application for HINK-E042A03-A1,
400 × 300 monochrome, two SSD1608 controllers, Raspberry Pi 5. No dashboard,
original workspace, daemon or GPIO activity required for import/offline use.
Python module APIs: `eink_driver.config`, `images`, `panel`, `transport`, `preflight`.

Exact driver port: modified GxEPD2_2IC 1.4.8 `GxEPD2_2IC_420_A03`, not generic
Waveshare 4.2-inch driver. GPL-3.0 source and pinned C++ reference included in
[eink_driver/upstream](eink_driver/upstream). Provenance and electrical
uncertainties: [SOURCES.md](eink_driver/upstream/SOURCES.md).

## Wiring

Always shut down Pi and disconnect **all** power reaching adapter before wiring,
ribbon inspection or resistor switch changes. Preserve existing fan connections.
Adapter SDA means SPI MOSI. BCM numbers differ from physical header pins.

| Adapter | BCM / function | Physical pin |
|---|---|---:|
| 3V3 | 3.3 V | 1 |
| GND | Ground | 14 |
| SDA | GPIO10 / MOSI | 19 |
| SCK | GPIO11 / clock | 23 |
| RST | GPIO17 | 11 |
| DC | GPIO25 | 22 |
| CS1 | GPIO8 | 24 |
| CS2 | GPIO7 | 26 |
| BUSY | GPIO24, input only | 18 |

No MISO connected. Logical left half defaults to adapter CS1, right to CS2.
Adapter names can differ from panel datasheet CS names; verify full-screen halves
visually. `--swap-cs` records explicit routing correction; never automatic.

## New Pi setup

Use Raspberry Pi OS with Python ≥3.11. Install distribution hardware bindings:

```sh
sudo apt install python3-venv python3-pip python3-setuptools python3-wheel python3-pil python3-lgpio python3-spidev
sudo usermod -aG gpio,spi "$USER"
```

Under `[all]` in `/boot/firmware/config.txt`, add:

```ini
dtoverlay=spi0-0cs,no_miso
```

Remove conflicting SPI overlays that claim GPIO7/8. Reboot for overlay and group
membership. Ordinary SPI enabling or `spidev.no_cs=True` alone does not free kernel
chip-select ownership. Transport discovers RP1 GPIO chip by label and GPIO line
names; no fixed gpiochip index. GPIO7/8 must be exclusively available before SPI
opens. On kernels rejecting SPI_NO_CS, driver requires live device-tree evidence
that native selects are unrouted.

Install wheel with apt-provided Pi libraries, without downloading dependencies:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-deps dist/eink_driver-0.1.0-py3-none-any.whl
.venv/bin/eink-driver preflight --output preflight-report
```

For source development, activate venv and use `python -m eink_driver`. Build wheel:
`python -m pip wheel --no-deps --no-build-isolation . -w dist`. Pillow ≥10,<13
required. On distributions shipping older Pillow, install supported version in
venv before use. Optional package extra `eink-driver[pi]` declares lgpio≥0.2.2 and
spidev≥3.6; no Arduino compilation needed at runtime.

Preflight reads model, OS, kernel, Python, libraries, SPI permissions, GPIO
ownership and pin modes. No output claims, reset, SPI writes or booster activity.
Optional `preflight --sample-busy` briefly claims only BUSY as input, then frees it.
Preflight fails while another display application owns GPIO; stop that application
before standalone hardware smoke. Successful SPI transmission cannot prove panel
presence because connection is write-only.

## Offline validation

```sh
python3 -m unittest discover -v
python3 scripts/reference_oracle.py validation/reference
python3 scripts/partial_reference_oracle.py validation/partial
python3 -m eink_driver dry-run --output validation/dry-example
python3 -m eink_driver mock --output validation/mock-example
```

Output directory for dry-run/mock/smoke must not already exist. Default is unique
run beneath `$XDG_STATE_HOME/eink-driver`, otherwise `~/.local/state/eink-driver`.
Runs save expected PNG, 15,000-byte frame, two row-wise 7,500-byte controller
buffers, configuration, code hashes and JSON result. Mock adds command events and
bounded BUSY traces. Dry-run creates artifacts only, with no transport or command
execution. Reference oracles need C++ compiler, use no hardware and compare actual
pinned C++ frame bytes, initialization/full-refresh/sleep and partial activation.

## One hardware refresh

1. Finish running display application's normal shutdown. Shut down Pi, disconnect
   all adapter power, allow discharge. Inspect wiring and ribbon seating/contact
   orientation. Leave resistor selector at **3 Ω**. Preserve fan connections.
2. Copy `config/inspection.example.json` to private inspection JSON. Replace observer
   and ISO date/time with UTC offset. Set required inspection booleans true only
   after actual checks. Example intentionally cannot authorize live hardware.
3. Restore power; ensure no other app owns panel. Run preflight, then explicit smoke:

```sh
.venv/bin/eink-driver preflight --output preflight-before-smoke
.venv/bin/eink-driver smoke --inspection /path/to/inspection.json --output smoke-new-run
```

Default smoke uses conservative SPI 100 kHz, mode 0, MSB first, active-high BUSY,
20-second BUSY limit, 60-second overall deadline. Reset HIGH/LOW/HIGH 10 ms each.
Maximum accepted SPI speed 4 MHz; existing dashboard runs at 4 MHz. Driver does not
change voltages, LUT values or booster settings; no OTP programming or retry.

Exactly one full refresh with unique run ID and asymmetric marks. Visually verify
**new** ID, correct orientation and complete image across both halves against PNG.
BUSY completion alone leaves hardware result INCONCLUSIVE; CLI never invents visual
PASS. Stop on abnormal heating, supply problems or stalled controller. Never remove
ribbon or change selector while powered or refreshing. GPIO cleanup is not physical
power removal. Do not measure resistance on powered hardware.

3 Ω remains experimental relative to SSD1608 reference 2.2 Ω. Live 0.47 Ω is blocked
without defensible adapter topology/RESE/booster evidence. `--resistor 0.47` works for
offline artifacts and records position; cannot change or detect physical switch.
Do not use blank screen as reason to switch resistors or blame adapter.

## Library use

```python
from eink_driver.config import Config
from eink_driver.images import pack, split_rows
from eink_driver.panel import Panel
from eink_driver.transport import Budget, FakeClock, mock_transport

config = Config(spacing=0, deadline=60)  # mock only; application owns live spacing
transport = mock_transport(config, Budget(config.deadline, FakeClock()))
panel = Panel(transport)
try:
    panel.init()                       # reset/init, booster remains off
    frame = bytes([255]) * 15_000      # 1 white, 0 black; MSB first
    panel.write_frame(frame)
    panel.refresh()                   # establish full baseline
    panel.power_off()
    changed = bytearray(frame)
    changed[0] = 0
    panel.update_changed(frame, changed)
    panel.power_off()
finally:
    panel.close()
```

Live applications must validate physical inspection and read-only preflight before
calling `live_transport`. They must provide overall wall-clock interruption handling,
refresh spacing and observations; library `Budget` checks bound waits but cannot
interrupt blocked kernel calls. CLI smoke provides SIGINT/SIGTERM/SIGALRM handling.

Partial update uses exact upstream 30-byte partial waveform. Full controller RAM
is uploaded for both halves, scan windows restored, then **one** partial activation
for all changed rows. Identical frame skips activation. This prevents prior narrow
window snow bands and multiple flashes. Full RAM upload does not mean full waveform.
Always establish full baseline before partial update; no partial endurance promise.
Original long-term spacing defaults conservative 180 s; dashboard's observed 10 s
update cadence is application policy, not documented panel lifetime guarantee.

Normal close powers booster off and sleeps only when controller state permits,
deasserts selects, closes SPI and frees GPIO. Failed controller state gets no further
panel commands; no extra refresh and no automatic restart. Investigate configuration,
transport, wiring, power circuitry, panel and driver before blaming one component.

## Validation recorded for this extraction

Mac software validation: 41 automated tests PASS; both compiled C++ reference
oracles PASS. Tests cover pins/input-only BUSY, chip selection/D-C, frame packing,
rotation/seam, reset, deadlines, BUSY failure and cleanup, no refresh in offline
commands, one mock refresh. Parent deployment also ran 41 driver tests and both reference oracles on Pi,
installed driver wheel, and completed full and partial hardware updates through
standalone dashboard. New visual confirmation remains INCONCLUSIVE; see
`validation/pi-deployment.json` and dashboard validation artifacts. Existing source had successful
user-observed full and partial updates on connected 3 Ω setup. No new electrical
measurements or 0.47 Ω hardware testing claimed.
