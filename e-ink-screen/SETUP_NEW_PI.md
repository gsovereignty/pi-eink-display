# Set up this e-paper display on a new Raspberry Pi

This guide reproduces the **working 3 Ω configuration** for the HINK-E042A03-A1
dual-controller panel. The original Pi passed white, black, opposite halves,
swapped halves, an asymmetric diagnostic image, sleep/reset/wake, and image
retention after all power was removed. Testing finished on 2026-10-08, Asia/Shanghai
(UTC+08:00). See [recorded results](evidence/RESULTS.md) and
[comparison table](runs/comparison.md).

## Hardware and proven software

| Item | Tested configuration |
|---|---|
| Computer | Raspberry Pi 5 Model B Rev 1.0 |
| Panel | HINK-E042A03-A1; markings `SYX 1734 2016-04-13` |
| Display | 4.2-inch, 400 × 300, monochrome, two controllers reported as SSD1608 |
| Adapter | Generic V1.5, 24-pin ribbon, separate CS1/CS2, physical resistor selector |
| Selector | **3 Ω**, visually confirmed while unpowered |
| OS | Debian 13.5 trixie, ARM64 Raspberry Pi kernel |
| Kernel | `6.18.34+rpt-rpi-2712` |
| Python | 3.13.5 |
| Libraries | lgpio 0.2.2.0, spidev 3.6, Pillow 11.1.0 |
| SPI | Mode 0, MSB first, 8-bit words, 100 kHz, no MISO |
| GPIO implementation | Direct lgpio; RP1 chip discovered by label and GPIO names |
| Driver | Local Python port of **GxEPD2_2IC_420_A03**, modified GxEPD2_2IC 1.4.8 |

These are observed versions, not a promise that other Pi models or kernels work
unchanged. Start with a 64-bit Raspberry Pi OS image providing Pi 5 support and
the packages below. Check its actual model/kernel/library versions using preflight.

Do not replace this driver with a generic Waveshare 4.2-inch driver. The pinned
original source, datasheets and hashes are in [evidence/upstream](evidence/upstream);
the port and source reasoning are in [evidence/SOURCES.md](evidence/SOURCES.md).
Exact-panel C++ SHA-256:
`367d84c71f79b6d57a2ed5f139437aabff074a28af7a65732634068d73d711a6`.

## 1. Prepare the new Pi and SSH

In Raspberry Pi Imager, choose a 64-bit OS supporting Pi 5. Configure a hostname,
user account, network access and SSH. Connect the development computer and Pi to
the same reachable network. Supply the new account's password locally when sudo
requires it; no password belongs in this guide or project configuration.

Original machine used `gareth@raspberrypi.local`. Its historical IPv4 address was
`192.168.50.191`, but direct IPv4 intermittently timed out; Bonjour hostname access
over IPv6 worked. DHCP addresses and IPv6 interface suffixes can change. Prefer
the hostname or obtain the new address from your router/console.

On the development computer, replace the hostname/account values as needed:

```sh
PI_TARGET=gareth@raspberrypi.local
PI_SOCKET="$HOME/.ssh/eink-pi"
ssh "$PI_TARGET" 'hostname; uname -a'
ssh -MNf -o ControlMaster=auto -o ControlPersist=yes -S "$PI_SOCKET" "$PI_TARGET"
ssh -S "$PI_SOCKET" "$PI_TARGET" 'hostname'
```

Use a different socket for each Pi. Public-key login is optional but convenient;
install your public key through your normal SSH setup. To check or close the
master connection:

```sh
ssh -O check -S "$PI_SOCKET" "$PI_TARGET"
ssh -O exit -S "$PI_SOCKET" "$PI_TARGET"
```

Recreate the master after a reboot if it disconnected. A stale socket does not
mean the Pi is online; an ordinary successful SSH command does.

## 2. Wire and inspect with all power disconnected

Shut down the Pi, disconnect **every source capable of powering the adapter**,
and allow discharge before wiring, handling the ribbon, or moving the selector.
Preserve the cooling fan's existing connections.

| Adapter label | BCM GPIO / function | Physical 40-pin header pin |
|---|---|---:|
| 3V3 | 3.3 V supply | 1 |
| GND | Ground | 14 |
| SDA | GPIO10 / SPI MOSI | 19 |
| SCK | GPIO11 / SPI clock | 23 |
| RST | GPIO17 | 11 |
| DC | GPIO25 | 22 |
| CS1 | GPIO8 | 24 |
| CS2 | GPIO7 | 26 |
| BUSY | GPIO24, **input only** | 18 |

**Physical pin numbers and BCM GPIO numbers are different.** SDA here is SPI MOSI,
not I²C. There is no MISO wire. Use 3.3 V, not a 5 V header pin.

Check ribbon seating, latch and contact direction, wiring against the table,
and visible damage/shorts. Set the selector to **3 Ω while unpowered**. Do not
disconnect the ribbon during a refresh or move the selector while powered.

The panel datasheet calls FPC pin 12 master `CS#` and pin 1 slave `CS1#`; these
names can differ from adapter labels. On the tested adapter, the port's normal
mapping worked: adapter CS1/BCM8 drives the left image half, CS2/BCM7 the right.
A different adapter still requires the visual halves tests or unpowered routing
checks. Never measure resistance or continuity on powered hardware.

## 3. Copy the complete software workspace

Original development copy: `~/git/hardware/e-ink-screen` on the development
computer. Original Pi copy: `/home/gareth/git/hardware/e-ink-screen`.
There is no required remote Git URL; copy the existing source directory.

The following assumes the new Pi account is `gareth`. Change remote paths if its
account differs. On the development computer:

```sh
cd ~/git/hardware/e-ink-screen
ssh "$PI_TARGET" 'mkdir -p /home/gareth/git/hardware/e-ink-screen'
rsync -a --exclude '__pycache__' --exclude '.venv' --exclude '.codebase-memory' --exclude 'runs' --exclude 'config/inspection.json' ./ "$PI_TARGET:/home/gareth/git/hardware/e-ink-screen/"
```

Keep the `hink_diag`, `tests`, `scripts`, `config` and `evidence/upstream` folders.
The oracle compiles the archived reference source. Do not reuse the old Pi's
inspection confirmation or old run observations as evidence for the new Pi.

## 4. Install packages and enable SPI without kernel-owned CS pins

On the Pi:

```sh
cd /home/gareth/git/hardware/e-ink-screen
sudo sh scripts/setup_pi.sh
sudo apt-get install --no-install-recommends -y build-essential
getent group gpio
getent group spi
sudo usermod -aG gpio,spi "$USER"
sudo reboot
```

`build-essential` supplies the C++ compiler for reference validation; it is not
needed for ordinary Python display updates. The `gpio` and `spi` groups must
exist before `usermod`; Raspberry Pi OS normally supplies them. Reboot/relogin
applies group membership. Run diagnostics as the ordinary user afterwards.

The setup script backs up `/boot/firmware/config.txt`, installs
`python3-lgpio python3-spidev python3-pil gpiod tmux`, and appends:

```ini
[all]
dtoverlay=spi0-0cs,no_miso
```

This enables SPI MOSI/clock while leaving GPIO7/8 available for **two manually
controlled chip selects** and GPIO9 unused. Keep active `dtparam=spi=on` and
conflicting `spi0-1cs`/`spi0-2cs` overlays disabled. The script stops when it finds
those conflicts; inspect the config and preserve unrelated/fan settings before
resolving them. Do not enable an ordinary two-CS SPI overlay instead.

No GPIO reset, booster command or refresh occurs during setup. No pip installation
is needed when running from the source directory with these system packages.

## 5. Verify access after reboot

Reconnect, then run on the Pi from the source directory:

```sh
id
ls -l /dev/spidev* /dev/gpiochip*
pinctrl get 7-11,17,24,25
python3 -m hink_diag preflight --hardware --sample-busy --runs runs-new-pi
```

Expected on the tested Pi: `/dev/spidev0.0`, GPIO10/11 in SPI mode, GPIO9 unused,
and GPIO7/8/17/24/25 without another GPIO consumer. The RP1 chip was
`/dev/gpiochip0`; `gpiochip4` was an alias. **Do not hard-code either number.**
Preflight discovers the appropriate chip and checks ownership. BUSY sampling
claims GPIO24 strictly as input; it does not reset the panel or write SPI.

Two compatibility details are already handled by this driver:

* spidev 3.6 lacks `open_path`; the port uses `open(bus, device)` after resolving
  the device path.
* The tested Pi's `dw-apb-ssi` controller rejects `SPI_NO_CS` with `EINVAL`.
  Fallback is allowed only after exclusive manual-CS GPIO claims and live
  device-tree verification of empty `cs-gpios` and effective `brcm,pins` limited
  to GPIO10/11. The fallback is logged. If evidence differs, it stops rather than
  guessing. Setting `spidev.no_cs` alone never frees kernel-owned GPIO7/8.

A successful SPI write proves host transmission only. There is no generic panel
ID read on this write-only connection. BUSY alone cannot prove both image halves.

## 6. Validate software before any refresh

```sh
python3 -m unittest discover -v
python3 scripts/reference_oracle.py
python3 -m hink_diag functional --runs runs-new-pi
python3 -m hink_diag smoke --mock --runs runs-new-pi
python3 -m hink_diag functional --mock --spacing 0 --runs runs-new-pi
```

The tested revision passed **38 automated tests** locally and on the Pi. The C++
oracle executes the actual archived exact-panel implementation against a mock
transport and verifies the init/full-refresh/sleep command sequence and both
7,500-byte controller streams. A full image is 15,000 bytes: each 50-byte row is
split into two 25-byte portions, not two contiguous framebuffer halves. Bit 7 is
leftmost; 1 means white and 0 black.

Default operation without `--hardware` or `--mock` is dry-run: PNG/bin artifacts,
no GPIO/SPI access or refresh. Mock success is not hardware success.

## 7. Record inspection and run one smoke update

After completing the physical checks, on the Pi:

```sh
cp config/inspection.example.json config/inspection.json
nano config/inspection.json
```

Fill observer, actual confirmation time (ISO format with `+08:00` when in Shanghai),
selector `"3"`, and each inspection fact only when verified. Record ambient and
starting retained image; leave unmeasured temperature/instruments unknown.

Use tmux so an SSH disconnect does not abandon the process:

```sh
tmux new-session -s e-ink-diagnostics
```

Inside tmux:

```sh
cd /home/gareth/git/hardware/e-ink-screen
python3 -m hink_diag signals --hardware --inspection config/inspection.json --deadline 30 --runs runs-new-pi
python3 -m hink_diag smoke --hardware --resistor 3 --spacing 0 --inspection config/inspection.json --runs runs-new-pi
```

Signal exercise is optional: clocks/MOSI while both selects are high, then select
pulses without clocks. No booster command. Without an analyzer its physical signal
quality remains inconclusive. Actual probe checks are in
[docs/OPERATIONS.md](docs/OPERATIONS.md).

Smoke performs one full update, normal booster-off and sleep. Compare the screen
with `runs-new-pi/SMOKE_RUN_ID/patterns/smoke.png`: it must show the **new run ID**,
correct orientation, complete border/corners/checkerboard and both halves.
Observe heating/supply behaviour. Record only what was observed or measured.

```sh
cp config/observations.example.json config/smoke-observations.json
nano config/smoke-observations.json
python3 -m hink_diag annotate runs-new-pi/SMOKE_RUN_ID config/smoke-observations.json
```

Replace `SMOKE_RUN_ID` with the printed ID. Set the JSON `run_id` to the same ID;
fill `steps.smoke` fields from observations. Do not mark retention before removing
all power. Annotation must report smoke PASS before proceeding.

## 8. Run functional tests and check retention

```sh
python3 -m hink_diag functional --hardware --resistor 3 --spacing 0 --inspection config/inspection.json --smoke-run runs-new-pi/SMOKE_RUN_ID --runs runs-new-pi
```

Smoke and functional commands must use the **same revision and settings**. The
interactive sequence is white, black, left-black/right-white, swapped halves,
asymmetric diagnostic, sleep/reset/wake and a new WAKE image. Each image requires
actual answers to visual, heating and supply questions before the next update.

`--spacing 0` reproduces the short supervised sequence explicitly requested during
the successful test. It removes additional waiting, not BUSY completion or manual
checks. Default spacing is 180 seconds, conservative general manufacturer guidance;
the HINK-specific minimum interval is unknown. For the conservative default, omit
`--spacing 0` from **both** smoke and functional commands. Neither mode is an
endurance test or a validated lifetime recommendation.

BUSY is active-high, each wait bounded to 20 seconds, overall default deadline
1,800 seconds. Tested update BUSY durations were approximately **1.60 seconds**.
No automatic retries, partial refresh, fast mode, OTP writes or voltage/LUT sweeps.
The tested reset pulse is HIGH 10 ms, LOW 10 ms, HIGH 10 ms. Fixed init values
include VCOM `a8` and the exact driver's full LUT; do not tune them blindly.

After the final successful update the driver sleeps and releases resources. Then:

```sh
sudo shutdown -h now
```

Wait for the Pi to halt. Disconnect every source that could energize the adapter,
allow discharge, and verify the **whole final WAKE image remains unchanged**.
Keep the ribbon connected and selector at 3 Ω. GPIO cleanup alone does not remove
physical power.

When the Pi is powered up again, save a functional observations JSON with its
actual run ID, all six observed `steps`, and
`retention.all_power_disconnected=true` / `retention.new_image_retained=true` only
after those checks. Annotate it and generate the comparison:

```sh
python3 -m hink_diag annotate runs-new-pi/FUNCTIONAL_RUN_ID config/functional-observations.json
python3 -m hink_diag comparison --runs runs-new-pi
```

The original completed [functional observations](runs/20261007-235812-9d1301/final-observations.json)
show the schema; use it only as a schema, never copy its verified facts to a new Pi.

## Troubleshooting and limits

Stop on abnormal heating, supply trouble, limits exceeded or a stalled controller.
Ctrl-C/deadline deasserts selects and releases GPIO/SPI; uncertain controller state
gets no further commands. Physical power must still be removed manually.

| Finding | Next discriminating check |
|---|---|
| SSH unavailable | Pi power/boot, router address, hostname resolution, SSH service; try hostname over IPv6 when IPv4 fails |
| No spidev device | Boot config/overlay, reboot, actual OS support |
| CS pins owned / fallback rejected | Kernel consumers and live pinctrl/device tree; resolve configuration instead of stealing lines |
| BUSY stuck or never asserts | Reset/BUSY wiring and measured signal transitions; do not automatically invert polarity or retry |
| Blank or incomplete image | Supply under load, ribbon contacts, MOSI/clock/DC/reset/CS capture, exact driver/version |
| Correct image but halves swapped | Adapter routing; documented `--swap-cs` change followed by a fresh smoke with matching functional settings |
| Persistent faults | Known-good panel/adapter substitution to distinguish driver, wiring, adapter and panel |

**0.47 Ω hardware tests remain blocked.** SSD1608 reference RESE is 2.2 Ω; 3 Ω
worked experimentally on this adapter, but that does not validate 0.47 Ω. Missing
adapter schematic/component ratings and exact-panel booster/RESE evidence prevent
a defensible second configuration. Never switch because an image is blank.

Original tests measured Pi SoC temperature (41.1 °C) and firmware flags
(`throttled=0x0`), not adapter/panel temperature, supply voltage or current. Adapter
voltage/current, switching peaks and component temperatures remain unavailable.
No conclusion that an adapter is defective follows from a failed update alone.

Each run saves JSONL events, configuration and code hashes, expected PNGs,
transmitted buffers, JSON/CSV results, observations and any supplied photographs.
Back up the complete workspace and new run directory after testing.

## Refresh-rate extension

The later benchmark revision passed 42 automated tests and permits nominal SPI
speeds up to 4 MHz. Ordinary diagnostics still default to 100 kHz. See
[REFRESH_RATE.md](docs/REFRESH_RATE.md) for the bounded three-frame command, fresh
matching-speed smoke requirement and measured full-frame throughput.

## Automatic process monitor

See [TOP_MONITOR.md](docs/TOP_MONITOR.md) for the ten-second CPU/memory averages,
boot-service installer, preview, operating commands and current validation.
Stop `eink-top.service` before running any other hardware diagnostic.

The service now defaults to the [resource dashboard](docs/DASHBOARD.md);
use `--layout table` for the original TOP rows. No additional dependency is required.
