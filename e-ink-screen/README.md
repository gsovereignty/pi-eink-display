# HINK-E042A03-A1 diagnostics

Runnable Pi 5 driver, CLI, automated tests and evidence archive. Exact
`GxEPD2_2IC_420_A03` full-refresh port; no arbitrary Waveshare driver.

[Executed results](evidence/RESULTS.md) · [Detailed operating guide](docs/OPERATIONS.md)
· [Source versions and uncertainties](evidence/SOURCES.md)
· [Resistor comparison](runs/comparison.md)

## Physical inspection before any refresh

1. Shut Pi down normally; disconnect **all** supplies/back-feed sources that
   could energize Pi or adapter. Allow discharge; confirm zero supply voltage if
   measuring. Never measure resistance/continuity while powered.
2. Inspect wiring below, ribbon seating/latch/contact direction, shorts, tears
   and corrosion. Preserve fan connections. Keep ribbon connected during refresh.
3. Set selector to **3 Ω while unpowered**; explicitly confirm position. Reconnect
   power after inspection. GPIO cleanup does not disconnect physical power.
4. Copy `config/inspection.example.json` to `config/inspection.json`; record
   observer/time, actual inspection facts, selector, ambient, starting retained
   image and available instruments. Leave unverified facts null.

| Adapter | BCM / function | Physical header |
|---|---|---|
| 3V3 | 3.3 V | 1 |
| GND | Ground | 14 |
| SDA | GPIO10 / SPI MOSI | 19 |
| SCK | GPIO11 / SPI clock | 23 |
| RST | GPIO17 | 11 |
| DC | GPIO25 | 22 |
| CS1 | GPIO8 | 24 |
| CS2 | GPIO7 | 26 |
| BUSY | GPIO24, **input only** | 18 |

BCM and physical pin numbers differ. SDA is MOSI, not I²C. No MISO.
Panel FPC pin 12 is master CS#, pin 1 slave CS1#; adapter names may differ.
Unpowered continuity or full-screen observations must establish routing.

## Pi setup

Working copy: `/home/gareth/git/hardware/e-ink-screen`.
SSH `gareth@raspberrypi.local`, dedicated socket `~/.ssh/raspberrypi`.

```sh
ssh -MNf -o ControlMaster=auto -o ControlPersist=yes -S "$HOME/.ssh/raspberrypi" gareth@raspberrypi.local
ssh -S "$HOME/.ssh/raspberrypi" gareth@raspberrypi.local 'hostname'
```

On Pi, from working copy:

```sh
sudo sh scripts/setup_pi.sh
sudo reboot
```

Setup saves boot-config backup and adds `dtoverlay=spi0-0cs,no_miso` under
`[all]`. Keep `dtparam=spi=on`/conflicting CS overlays disabled. Installs
`python3-lgpio python3-spidev python3-pil gpiod tmux`. Existing fan configuration
is preserved. `spidev.no_cs` alone cannot free kernel-owned GPIO7/8: preflight
and exclusive claims verify ownership. No refresh during setup.

System Python dependencies already installed on this Pi. No pip needed.
Elsewhere: `python3 -m pip install -e .`; optional Pi dependency group is `[pi]`.
Built wheel available in `dist/`; full source checkout needed for C++ oracle.
Remove temporary sudo rule after setup with
`sudo rm /etc/sudoers.d/90-epaper-diagnostics` if that rule was enabled.

## Validation and staged tests

```sh
python3 -m unittest discover -v
python3 scripts/reference_oracle.py
python3 -m hink_diag functional --runs runs
python3 -m hink_diag smoke --mock --runs runs
python3 -m hink_diag functional --mock --runs runs
python3 -m hink_diag preflight --hardware --sample-busy --runs runs
```

Default **dry-run** creates PNGs/buffers without transport or refresh. Mock
uses virtual time and fake GPIO/SPI. C++ oracle executes archived driver to
verify both 7500-byte row-wise streams plus init/refresh/sleep trace. Preflight
checks model/OS/kernel/Python, devices, permissions and GPIO ownership;
`--sample-busy` claims only BUSY input briefly. No reset/booster/SPI write.

Optional multimeter: adapter supply to GND should be near 3.3 V, within panel
VCI operating limits 2.4–3.7 V; verify loaded voltage during approved refresh.
Panel operation 0–50°C. Record actual readings only. Average current and switching
peaks differ; adapter-specific current/thermal ratings unknown. Analyzer checks
clock/MOSI/DC/reset/both selects/BUSY at 3.3 V, mode 0, MSB first, 100 kHz.
Exact probe locations and expected trace in [operating guide](docs/OPERATIONS.md).

After inspection, optional signal exercise keeps both CS high during SPI,
then pulses each CS without clocks. No booster command:

```sh
python3 -m hink_diag signals --hardware --inspection config/inspection.json --deadline 30 --runs runs
```

Run actual tests in persistent tmux session `e-ink-diagnostics`. If it exists,
attach instead of creating another. Normal `tmux` after setup; before setup,
rootless wrapper `/home/gareth/.local/bin/epaper-tmux` is installed.

```sh
ssh -t -S "$HOME/.ssh/raspberrypi" gareth@raspberrypi.local '/home/gareth/.local/bin/epaper-tmux attach-session -t e-ink-diagnostics'
```

Inside Pi session, from working copy:

```sh
python3 -m hink_diag smoke --hardware --resistor 3 --inspection config/inspection.json --runs runs
```

One full refresh, then normal booster-off/sleep. Verify **new visible run ID**,
whole image, orientation, both halves, corners and seam against saved PNG.
Old retained image, successful SPI write or BUSY alone is insufficient.
Record actual facts using observations template; optional photos copied into run.

```sh
python3 -m hink_diag annotate runs/ACTUAL_SMOKE_ID config/smoke-observations.json
python3 -m hink_diag functional --hardware --resistor 3 --inspection config/inspection.json --smoke-run runs/ACTUAL_SMOKE_ID --runs runs
```

Functional run requires observed smoke PASS with same revision/config and
interactive per-image observations. Sequence: white, black, opposite halves,
swapped halves, asymmetric diagnostic, sleep/reset/wake and further unique update.
Unknown/failed observation stops remaining sequence. Booster off between updates;
180 s default spacing, 20 s BUSY waits, 1800 s overall deadline. No partial modes,
endurance loops or automatic refresh retries. Spacing is conservative general
manufacturer guidance; exact HINK minimum unavailable.

Stop immediately for abnormal heating, supply problems, limits exceeded or stall.
Ctrl-C/SIGTERM/deadline deassert CS and release resources; uncertain controller
state gets no further commands. Physical power remains connected: disconnect it
and investigate before rerunning. Software cannot cut power or recover wedged kernel.

After successful final sleep, shut Pi down and disconnect **all** adapter power.
Observe retention of final unique image; record power removal/retention and
annotate functional result. Complete hardware PASS requires all intended images,
correct orientation/both halves and retention. Electrical readings remain null
unless measured.

## 3 Ω versus 0.47 Ω

```sh
python3 -m hink_diag functional --mock --resistor 0.47 --runs runs
python3 -m hink_diag smoke --resistor 0.47 --runs runs
python3 -m hink_diag comparison --runs runs
```

Selector is physical; option only records it. SSD1608 reference circuit uses
**2.2 Ω RESE**. 3 Ω is monitored experimental baseline; **live 0.47 Ω execution
blocked** without circuit/component ratings and exact-panel validation. Both
software suites implemented. Never switch to 0.47 Ω because 3 Ω is blank.

If evidence later justifies 0.47 Ω: review execution gate; finish normal shutdown,
disconnect every energizing source, discharge, switch unpowered, explicitly
confirm new position. Keep ribbon seated. Repeat smoke before functional tests.
Match revision/init/SPI/patterns/timing/ambient and recorded common starting image.
Current first smoke establishes function, not a matched resistor comparison.

Each run saves timestamped logs (+08:00), configuration/code manifest, expected
PNGs, transmitted buffers, JSON/CSV, observations and supplied photos. Comparison
marks PASS/FAIL/NOT RUN/INCONCLUSIVE; mocks never count as hardware PASS.

Absent SPI currently ranks Pi configuration first. Next: captured transport,
unpowered wiring/ribbon/CS continuity, driver/batch compatibility, adapter supply
circuitry, panel. [Failure-isolation guide](docs/OPERATIONS.md#failure-isolation-and-saved-evidence)
provides discriminating tests. Without known-good substitutes, failed update
cannot prove adapter defective.

Pi compatibility: spidev 3.6 uses `open(bus, device)` when `open_path` is absent.
On this Pi, dw-apb-ssi rejects `SPI_NO_CS`. The harness permits that fallback
only after exclusive manual-CS claims and live device-tree checks proving empty
`cs-gpios` and SPI pinctrl restricted to GPIO10/11. Every fallback is logged.

User-requested short supervised sequence on 2026-10-07 used `--spacing 0`.
This removes only the additional inter-refresh delay; BUSY completion, normal
power-off and manual checks remain mandatory. HINK minimum spacing is unknown;
default stays 180 s. Repeat both resistor configurations with identical spacing.

Latest actual outcome: **3 Ω complete-system PASS**, including both halves,
asymmetric diagnostic image, sleep/reset/wake and retention after all power removal.
38 automated tests pass on host and Pi. **0.47 Ω NOT RUN**, blocked by missing
adapter RESE/booster evidence. Electrical supply/current and panel/adapter temperature
remain unmeasured. See [results](evidence/RESULTS.md) and [comparison](runs/comparison.md).
Final retention annotation saved locally while Pi is powered off; remote software
and raw functional logs were already saved before shutdown.

Refresh-rate testing: [bounded full-refresh benchmark](docs/REFRESH_RATE.md).
Fresh-Pi reproduction: [SETUP_NEW_PI.md](SETUP_NEW_PI.md).

Static desktop capture: [desktop snapshot command](docs/DESKTOP.md).

Automatic process monitor: [10-second top averages and boot service](docs/TOP_MONITOR.md).

Resource dashboard (default boot display): [layout, telemetry and commands](docs/DASHBOARD.md).
