# E-ink Dashboard

Bitcoin mainnet dashboard now available: [Bitcoin layout, API and commands](BITCOIN.md). Run `eink-bitcoin`; system dashboard remains `eink-dashboard`.

Independent Raspberry Pi application. Uses separate `eink-driver` package; no dependency on original diagnostics checkout. GPL-3.0; bundled driver reference carries upstream notices.

400 × 300 monochrome dashboard: CPU and four core bars, SoC temperature, RAM/swap, disk space and activity, five-minute CPU/RAM history, IP addresses, RX/TX per minute, cumulative interface bytes since boot, top processes, uptime and Wi-Fi signal. Ten-second measured averages; timestamps Asia/Shanghai (+08:00). Missing metrics show `--`. Cumulative network counters reset when interface is recreated, not only at boot.

First update establishes full-screen baseline. Later updates upload both complete controller RAM images and activate one partial waveform. This fixed observed snow bands; no black/white clearing between updates. Partial waveform remains experimental for this recovered panel; prolonged ghosting/endurance has not been established. Restart creates a new full baseline. No automatic retry after controller failure.

## Hardware

Exact panel: HINK-E042A03-A1, dual SSD1608 controllers. Generic V1.5 dual-CS adapter, physical selector **3 Ω**. 0.47 Ω remains unvalidated; app refuses that configuration. Selector cannot be changed or verified by software.

| Adapter | BCM/function | Physical pin |
|---|---|---:|
| 3V3 | 3.3 V | 1 |
| GND | Ground | 14 |
| SDA | GPIO10 / SPI MOSI | 19 |
| SCK | GPIO11 / SPI clock | 23 |
| RST | GPIO17 | 11 |
| DC | GPIO25 | 22 |
| CS1 | GPIO8 | 24 |
| CS2 | GPIO7 | 26 |
| BUSY | GPIO24 input | 18 |

SDA means SPI MOSI; no MISO. Preserve fan wiring. Disconnect all adapter power before checking ribbon/wiring or changing selector; allow discharge. Never disconnect ribbon or move selector during powered operation. Stop on abnormal heat or supply problems. Software cleanup does not remove physical power.

Driver discovers RP1 GPIO chip, uses lgpio and spidev. SPI mode 0, MSB first, 4 MHz established on this setup; BUSY active-high, bounded 20-second waits, 60-second budget per update. Separate GPIO chip selects require kernel to release GPIO7/8: `spidev.no_cs` alone is insufficient.

## New Pi installation

Use Raspberry Pi OS with Python 3.11+ and Pi 5-compatible lgpio. Install OS packages:

```sh
sudo apt update
sudo apt install python3-venv python3-pip python3-setuptools python3-wheel python3-pillow python3-lgpio python3-spidev procps iproute2 fonts-dejavu-core
sudo usermod -aG gpio,spi "$USER"
```

Add under `[all]` in `/boot/firmware/config.txt`:

```ini
dtoverlay=spi0-0cs,no_miso
```

Reboot to apply overlay and group membership. Check `/dev/spidev0.0` exists. Do not retain another SPI overlay claiming CE0/CE1. Read driver README for ownership checks and electrical limits.

Copy both project directories (or both wheels) onto Pi. From dashboard directory:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-deps ../eink-driver/dist/eink_driver-0.1.0-py3-none-any.whl dist/eink_dashboard-0.2.0-py3-none-any.whl
mkdir -p ~/.config/eink-dashboard
cp config/inspection.example.json ~/.config/eink-dashboard/inspection.json
```

Pillow must satisfy version 10–12; if OS package is older, install a matching version into venv. Edit inspection file only after actual powered-off inspection: enter observer, ISO timestamp including offset, selector `3`, and truthful required booleans. Retain unavailable readings as null. Do not copy someone else's confirmation onto new hardware.

Commands:

```sh
# Capture dashboard PNG and metrics without opening display GPIO/SPI.
.venv/bin/eink-dashboard --windows 1
# Mock display commands; real Linux telemetry, no panel access.
.venv/bin/eink-dashboard --mock --windows 2
# Explicit hardware operation; first full update, then partial updates.
.venv/bin/eink-dashboard --hardware
# Enable automatic startup; stops prior eink-top service if present.
sudo scripts/install-service.sh "$USER"
```

Default state: `~/.local/state/eink-dashboard`; inspection: `~/.config/eink-dashboard/inspection.json`. XDG_STATE_HOME and XDG_CONFIG_HOME supported. `--state-dir`/`--inspection` override paths. `--layout table` provides process-table view; `--clear-cycle full` forces one full refresh per update. `black-white` explicitly enables three full refreshes and is not default.

```sh
systemctl status eink-dashboard --no-pager
journalctl -u eink-dashboard -n 20 --no-pager
sudo systemctl stop eink-dashboard
sudo systemctl disable eink-dashboard
```

Do not run another hardware application while service owns display. SIGINT/SIGTERM stop sampling and perform valid controller shutdown where state permits, then release GPIO. For rollback, stop/disable `eink-dashboard` before enabling previous `eink-top`; original diagnostics remains intact.

## Artifacts and validation

State contains latest expected PNG, 15,000-byte packed image, two row-split 7,500-byte controller buffers, raw top text, JSON metrics, bounded history, source fingerprints, preflight and shutdown records. SPI write completion is not visual proof; inspect new image across whole screen.

```sh
PYTHONPATH=.:../eink-driver python3 -m unittest discover -v
python3 -m pip wheel --no-deps --no-build-isolation . -w dist
```

Tests cover telemetry parsing, sample weighting, process identity, network windows and counter resets, renderer, refresh orchestration and failure paths. Driver package has additional transport/image/controller tests. See `VALIDATION.md` for checks actually run during packaging.
