# Bitcoin e-ink dashboard

Now extracted into [independent Bitcoin app](../eink-bitcoin/README.md). Active Pi service uses that app’s own venv and configuration. This integrated version is preserved for rollback.

Runnable Bitcoin mainnet dashboard in `epaper_dashboard/bitcoin.py`, command `eink-bitcoin`. Included in `eink-dashboard` 0.2.0; original system dashboard command remains available. Uses installed independent exact-panel `eink-driver` 0.1.0; same 3 Ω wiring, GPIO ownership and inspection guard.

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

## Install and run

Follow [hardware/new Pi setup](README.md) first. From project directory, using existing venv and driver:

```sh
.venv/bin/python -m pip install --no-deps dist/eink_dashboard-0.2.0-py3-none-any.whl
# Live API preview, no GPIO access:
.venv/bin/eink-bitcoin --windows 1
# Offline deterministic preview:
.venv/bin/eink-bitcoin --fixture tests/fixtures/bitcoin.json --windows 1
# One mock refresh:
.venv/bin/eink-bitcoin --mock --fixture tests/fixtures/bitcoin.json --windows 1
# Explicit panel operation, after stopping other display owners:
.venv/bin/eink-bitcoin --hardware
# Automatic startup; gracefully stops/disables system dashboard and old eink-top:
sudo scripts/install-bitcoin-service.sh "$USER"
```

Default state `~/.local/state/eink-bitcoin`; default inspection `~/.config/eink-dashboard/inspection.json`. XDG_STATE_HOME/XDG_CONFIG_HOME supported; command-line path overrides available. `--api-base` supports a compatible self-hosted mainnet instance. `--fixture` reads a saved snapshot instead of network; fixture timestamps/data remain historical and must not be presented as live readings.

Saved state: expected PNG, packed 15,000-byte image, row-split 7,500-byte CS1/CS2 buffers, current JSON snapshot and per-endpoint cache, latest update/BUSY result, startup settings and runtime source fingerprints, preflight, events and stopped record. Update records also go to persistent system journal.

```sh
systemctl status eink-bitcoin --no-pager
journalctl -u eink-bitcoin -n 20 --no-pager
sudo systemctl stop eink-bitcoin
# Switch back to CPU/system dashboard; disables Bitcoin service first:
sudo scripts/install-service.sh "$USER"
```

Only one display owner at a time. Game mirroring must also be stopped before either dashboard. Bitcoin dashboard does not change desktop resolution, fan wiring, physical resistor or game state. Service has no restart loop after hardware errors. SIGINT/SIGTERM release resources; normal shutdown powers controller off/sleeps only in valid state. Stop service before removing adapter power.

Persistent live Pi logs: tmux session `bitcoin-eink`, window `logs`. Current installation `/home/gareth/git/hardware/eink-dashboard`; installed CLI works outside checkout.

## Reproduce validation

```sh
PYTHONPATH=.:../eink-driver python3 -m unittest discover -v
python3 -m pip wheel --no-deps --no-build-isolation . -w dist
```

Fixture is a recorded public API snapshot, not a claim of current Bitcoin values. Packaging/actual hardware validation recorded under `validation/bitcoin/`; fresh visual confirmation required for whole-panel PASS. No new electrical measurements, 0.47 Ω runs or endurance tests.
