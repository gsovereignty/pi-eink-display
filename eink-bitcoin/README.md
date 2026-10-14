# Bitcoin E-Ink

Independent Bitcoin mainnet application, distribution `eink-bitcoin` 0.1.0, package `bitcoin_eink`, executable `eink-bitcoin`. No imports or runtime dependency on system dashboard or original diagnostics. Uses separate reusable `eink-driver` 0.1.0; driver wheel included in `dist/`. GPL-3.0.

## Screen

- Large BTC/USD price and derived sats per dollar; quote's own age displayed.
- Latest returned block height and elapsed time since its timestamp.
- Mempool.space fee estimates for approximately 10, 30 and 60 minutes, in sat/vB. Estimates, not confirmation guarantees; decimals retained.
- Unconfirmed transaction count and mempool virtual size in **MvB**, not physical MB.
- Three recent blocks, transaction counts and ages.
- Projected difficulty change and blocks remaining before retarget.
- API/cached/error status, oldest endpoint fetch age, local clock Asia/Shanghai (+08:00).

No invented 24-hour return or historical chart. API quotes are aggregate service quotes, not exchange execution prices. Endpoints can update at different times; view is not atomic chain snapshot. Quote age and block ages use API timestamps. Fees and difficulty are API estimates; no trading recommendation or transaction execution.

## API and cache

Default host `https://mempool.space/api`. Five requests once per 60-second poll, no API key. Official docs: [REST API](https://mempool.space/docs/api/rest), [upstream endpoint documentation](https://github.com/mempool/mempool/blob/master/frontend/src/app/docs/api-docs/api-docs-data.ts).

| Endpoint | Used fields |
|---|---|
| `/v1/prices` | USD, quote time |
| `/v1/fees/recommended` | fastestFee, halfHourFee, hourFee |
| `/mempool` | count, vsize |
| `/v1/blocks` | height, timestamp, tx_count; first three blocks |
| `/v1/difficulty-adjustment` | difficultyChange, remainingBlocks |

Each successful endpoint replaces only its own cache entry after schema/number validation. Failures preserve last good data, its original timestamp and error. `*` marks sections cached because that endpoint failed or last successful fetch is over three minutes old. Missing initial data shows `--`/unavailable. Quote age remains visible even when HTTP request succeeds. Cache survives restart; no fabricated replacement values. Malformed/missing/non-finite rendered numbers rejected. Network calls have six-second socket timeout, eight-second wall-clock limit and 1 MiB response cap; no immediate request retries. Failed endpoints tried at next scheduled poll. Default five requests per minute; respect hosting instance policy when changing interval/base URL. Minimum interval 30 seconds.

API cache failure does not trigger extra controller refresh retries. First image establishes full baseline; subsequent changed images use one partial waveform with complete controller RAM uploads. Identical image skips activation. Same bounded BUSY waits, per-update 60-second wall-clock limit, valid-state cleanup and no automatic service restart. No intermediate white/black screens. Long-term partial-refresh ghosting/lifetime not validated; restart establishes full baseline. Stop on abnormal heating/supply problems. GPIO cleanup does not disconnect power.

## Hardware and new Pi setup

Pi 5, HINK-E042A03-A1 400 × 300 monochrome dual-controller panel, V1.5 adapter, inspected physical 3 Ω position. 0.47 Ω unvalidated and blocked. SDA means SPI MOSI; no MISO.

| Adapter | BCM/function | Physical pin |
|---|---|---:|
| 3V3 | 3.3 V | 1 |
| GND | Ground | 14 |
| SDA | GPIO10 / MOSI | 19 |
| SCK | GPIO11 / clock | 23 |
| RST | GPIO17 | 11 |
| DC | GPIO25 | 22 |
| CS1 | GPIO8 | 24 |
| CS2 | GPIO7 | 26 |
| BUSY | GPIO24 input | 18 |

Preserve cooling fan connections. Before inspecting wiring/ribbon or changing selector, disconnect all power that can energize adapter and allow discharge. Never switch while powered or disconnect ribbon during refresh. Do not measure resistance on powered hardware. No new electrical readings are inferred from successful writes.

Raspberry Pi OS, Python 3.11+, Pi 5-compatible lgpio and SPI required:

```sh
sudo apt update
sudo apt install python3-venv python3-pip python3-setuptools python3-wheel python3-pillow python3-lgpio python3-spidev fonts-dejavu-core
sudo usermod -aG gpio,spi "$USER"
```

Under `[all]` in `/boot/firmware/config.txt`:

```ini
dtoverlay=spi0-0cs,no_miso
```

Remove conflicting SPI overlays that claim GPIO7/8; do not edit unrelated fan settings. Reboot to apply overlay/group membership. Check `/dev/spidev0.0`. Driver discovers RP1 GPIO chip; mode 0, 4 MHz, MSB first. Kernel must release both chip selects: `spidev.no_cs` alone is insufficient.

From this project directory:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-deps dist/eink_driver-0.1.0-py3-none-any.whl dist/eink_bitcoin-0.1.0-py3-none-any.whl
mkdir -p ~/.config/eink-bitcoin
cp config/inspection.example.json ~/.config/eink-bitcoin/inspection.json
```

Pillow must be version 10–12; if OS package is older, run `.venv/bin/python -m pip install "Pillow>=10,<13"`. Fill inspection JSON with real observer, offset-aware ISO timestamp and truthful required booleans after powered-off checks. Do not reuse another device's confirmation. Existing Pi migration preserves its previously confirmed inspection for unchanged hardware.

## Commands and boot service

```sh
# Live API preview, no GPIO access:
.venv/bin/eink-bitcoin --windows 1
# Offline historical fixture:
.venv/bin/eink-bitcoin --fixture tests/fixtures/bitcoin.json --windows 1
# One mock refresh:
.venv/bin/eink-bitcoin --mock --fixture tests/fixtures/bitcoin.json --windows 1
# Explicit display access; stop other display owners first:
.venv/bin/eink-bitcoin --hardware
# Install and enable boot service:
sudo scripts/install-service.sh "$USER"
```

Installer validates inspection and unit before migration, gracefully stops current Bitcoin service and disables previous known dashboard services, preserves old unit backup, then enables/starts `eink-bitcoin.service`. New service uses only this app's own venv and config; works outside checkout. `Restart=no` prevents hardware retry loops. Boot enablement is checked; a fresh reboot is not required merely to migrate application.

Default state `~/.local/state/eink-bitcoin`; inspection `~/.config/eink-bitcoin/inspection.json`. XDG_STATE_HOME/XDG_CONFIG_HOME and explicit CLI overrides supported. `--api-base` supports compatible mainnet API, `--interval` defaults 60 seconds (minimum 30), `--windows` bounds polls. `python -m bitcoin_eink` equivalent to executable.

```sh
systemctl status eink-bitcoin --no-pager
journalctl -u eink-bitcoin -n 20 --no-pager
sudo systemctl stop eink-bitcoin
sudo systemctl disable eink-bitcoin
```

Only one panel owner. Stop service before running diagnostics/game mirror or removing adapter power. SIGINT/SIGTERM shut down valid controller state, then free GPIO/SPI; failed state gets no extra refresh. GPIO cleanup does not physically disconnect power. Full baseline at startup, then same single partial waveform per changed update; no intermediate black/white clearing. No desktop resolution or game-state changes.

State saves expected PNG, 15,000-byte full buffer, row-split 7,500-byte CS1/CS2 buffers, API snapshot and cache, update/BUSY metadata, source hashes, preflight and shutdown/event records. Journal stores per-update JSON logs. Hardware visual PASS requires manually confirmed new complete image across both halves.

## Reproduce software checks

```sh
.venv/bin/python -m unittest discover -v
.venv/bin/python -m pip wheel --no-deps --no-build-isolation . -w dist
```

Fourteen app tests cover API/cache failures, schema validation, quote/fee values, renderer packing, no hardware/network during fixture capture, mock refresh and wall-clock timeout cleanup. Separate reusable driver includes transport/controller/reference tests. See `validation/RESULTS.md` for checks actually executed during extraction.

Source archive and app/driver wheels under `dist/`; SHA256SUMS records release hashes. No API keys or personal inspection confirmations shipped as defaults.
