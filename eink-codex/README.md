# Codex E-Ink

Standalone `eink-codex` 0.5.0 app for Pi 5 and HINK-E042A03-A1 400 × 300 monochrome e-paper. Reuses bundled `eink-driver` 0.1.0. No Bitcoin/system dashboard imports or desktop capture. GPL-3.0.

Displays combined active agents, waiting subset, idle and failed sessions, per-machine active/waiting/idle/status rows, seven-day allowance remaining and reset countdown, extra-reset availability and expiry countdowns, WireGuard handshake age, and Nostrocket membership. Refreshes telemetry every 15 seconds, not a claimed instantaneous count. All clock labels use Asia/Shanghai (+08:00).

## Count meaning

Reads **actual loaded thread states** from Codex's managed app-server, not `pgrep` counts. Active includes threads waiting on approval/user input; WAITING is that subset, not additional agents. Child classification uses `parentThreadId`. Loaded IDs are paginated and deduplicated; historical/notLoaded threads excluded. Connection/read failure shows `--`, never fabricated zero. Telemetry RPC is read-only: initialize, loaded list, metadata reads and account limits. It never starts agents, answers approvals, resets quota, or changes tasks. Account tokens, balances, account IDs and reset-credit IDs are not saved in dashboard snapshots.

Local telemetry comes from this Pi's managed daemon; configured remote hosts add their own managed-daemon states. Normal current Codex TUI uses shared daemon; make it explicit with:

```sh
~/.local/bin/codex --remote unix:// --cd ~/git
~/.local/bin/codex agents
```

The **CLI processes** figure is informational and may overlap managed TUI sessions; it is never added to agent counts. Independent `codex exec` and `--no-daemon` children/state are unavailable through the shared daemon. Configured MacBook and Mac mini agents are included through SSH collectors. Other machines/cloud agents remain outside scope. Threads can change state between individual RPC reads, so snapshot is not atomic. All loaded threads are counted; three machine rows fit the current display. Model labels are configured thread models, not per-turn billing/model evidence.

Network status comes from a fixed root helper, `/usr/local/lib/pi-codex/network-status.py`, writing `/run/pi-codex-network.json` every 15 seconds. Older than 45 seconds shows unavailable/stale. A recent WireGuard handshake proves peer contact, not all application requests. ZeroTier `ACCESS_DENIED` explicitly means membership unauthorized, not connected.

## Machines over ZeroTier

Default fleet: Pi, MacBook via `codex-macbook` (gareth@10.46.107.74), Mini via `codex-mac-mini` (g@10.46.107.110). Existing pinned host keys, unattended key authentication and persistent per-host SSH sockets used as gareth. No SSH credentials are bundled. Pi must already have these aliases and read access to `~/.local/lib/codex-status/query.py`; see separately supplied CODEX_STATUS_SSH.md for key setup/rollback.

Each poll sends existing collector to `/opt/homebrew/bin/python3.14 -` over SSH. Collector reads each Mac's **existing** daemon; no agent starts, resumes, stops, prompts or queue edits. Bounded remote execution: eight-second SIGALRM on Mac, twelve-second SSH subprocess deadline on Pi, connection timeout four seconds. No immediate SSH retry. Both SSH queries execute concurrently with Pi's local telemetry; whole telemetry phase retains 35-second deadline. Remote collector file preserved unchanged.

Collector contract: observedAt must have timezone, socketReadable true, loadedThreadCount consistent with threads, each thread id and runtimeState.type/activeFlags. IDs deduplicated within host, distinct hosts remain separate agent instances. Unknown states, partial read errors, malformed payloads, old timestamps or excessive clock difference make that host unavailable, never zero agents. active includes children and waiting subset; notLoaded excluded. Parent details absent in remote contract, so global root/child counts unavailable.

Combined headline includes only current successful hosts. If any missing, counts marked `*` and footer says PARTIAL n/3 hosts. Machine row shows `--` and STALE immediately after failure when cached success is at most 45 seconds old; otherwise OFFLINE (telemetry unavailable, not proof machine is powered off). Cached numbers are not included in totals. No hosts available means unknown (`--`), not zero. Cache survives service restart in hosts-cache.json. Snapshot records per-host observation/error/last-good information; times retain offsets. Pi's account usage/extra-reset data shown once, never summed across machines.

`--local-only` disables SSH entirely. `--collector PATH` selects already-provisioned collector. Default host registry is `DEFAULT_HOSTS` in codex_eink/fleet.py; add a provisioned alias there and rebuild/reinstall to extend fleet. Each host requires its own persistent SSH socket. No new HTTP publisher, listener, ACP adapter or account credentials needed.

```sh
ssh codex-macbook '/opt/homebrew/bin/python3.14 -' < ~/.local/lib/codex-status/query.py
ssh codex-mac-mini '/opt/homebrew/bin/python3.14 -' < ~/.local/lib/codex-status/query.py
.venv/bin/eink-codex --local-only --windows 1
.venv/bin/eink-codex --windows 1
```

## Automatic login recovery

Live hardware mode detects explicit authentication failures from Pi's usage API
before truncating diagnostic text. It starts one `codex login --device-auth`
process and replaces the quota area with the sign-in URL, current one-time code,
and expiry countdown. Agent counts and machine rows stay visible. Open
https://auth.openai.com/codex/device on your phone/computer and authorize that
code with your ChatGPT account. No password entry on Pi is needed.

Login runs outside telemetry deadlines and never blocks polling. A failed or
expired attempt clears its code and retries after 60 seconds; an outstanding
attempt never creates another login. Successful sign-in reloads Pi's daemon
only once local active-agent count is known to be zero. Reload failures retry
the reload, not the login. Remote Mac agents are unaffected. The service
installer enables user lingering; a separate systemd user scope keeps the
reloaded daemon outside the display service's process group.

Capture-only mode, mock mode and fixtures never start login or reload anything.
`--no-auth-recovery` also disables recovery on live hardware. Service shutdown
terminates its pending login. One-time code appears in the current snapshot and
preview image until the next healthy poll; account tokens remain exclusively
in Codex's login storage and are never copied to dashboard state. Ordinary
network/server errors do not trigger sign-in.

## Usage and expiry panel

Visible window identified by actual `windowDurationMins` (10080 for 7 days), never by primary/secondary slot. Five-hour panel removed to make room for machine table; backend normalization still accepts other window data. Remaining percentage is 100 minus API usedPercent, clipped at zero. Missing seven-day window shows unavailable; no inferred allowance. Reset/expiry times are server Unix timestamps. Countdowns rounded up to minutes; day/hour/minute display, no negative countdown. Due reset says "Due / awaiting API" and keeps reported usage until server confirms new allowance. A passed expiry says EXPIRED, not automatically renewed.

Extra-reset availableCount is server-reported, independent of quota percentages. Only available-status credit expiries displayed, earliest first. Missing count differs from zero; missing expiry shows unavailable. If more than three credits, pages rotate each minute to show every expiry; no additional per-second refreshes. Dashboard reads account/rateLimits/read only and never redeems resets. Percentage/count are latest API readings, not predictions. API error shows usage unavailable, not full allowance.

Top header bar removed; larger combined counts and roomier per-machine table remain above usage panel. Clock lives in footer. Remote collectors do not return parent identity, so no global root/child breakdown is inferred. Full thread metadata remains in snapshot.json. Network footer uses minute-resolution handshake age so unchanged values do not create needless countdown refreshes. Default polling remains 15 seconds; minute-resolution countdowns and identical-frame skipping limit physical updates. First launch/reset still establishes one full baseline, then ordinary changed-image partial updates.

## Install

Requires Python 3.11+, Pillow 10–12, websockets 15–16, Codex authenticated managed daemon, Pi GPIO/SPI dependencies and actual inspected wiring. Full pin/overlay setup is documented in [reusable driver](../eink-driver/README.md). Included driver wheel allows installation without that sibling checkout.

```sh
sudo apt install python3-venv python3-pip python3-setuptools python3-wheel python3-pillow python3-lgpio python3-spidev fonts-dejavu-core
python3 -m venv --system-site-packages .venv
.venv/bin/pip install "websockets>=15,<17" "Pillow>=10,<13"
.venv/bin/pip install --no-deps dist/eink_driver-0.1.0-py3-none-any.whl dist/eink_codex-0.5.0-py3-none-any.whl
```

Use `dtoverlay=spi0-0cs,no_miso` under `[all]` in `/boot/firmware/config.txt` and `sudo usermod -aG gpio,spi "$USER"`. Remove conflicting overlays that own GPIO7/8; preserve fan setup. Reboot after these kernel/group changes. Driver discovers RP1 GPIO chip, uses lgpio and spidev, SPI mode 0, 4 MHz, MSB first, manual independent CS and simultaneous reference selection. `spidev.no_cs` alone does not release kernel chip-select ownership.

| Adapter | BCM/function | Physical pin |
|---|---|---:|
| 3V3 | 3.3 V | 1 |
| GND | Ground | 14 |
| SDA | GPIO10 / SPI MOSI | 19 |
| SCK | GPIO11 / clock | 23 |
| RST | GPIO17 | 11 |
| DC | GPIO25 | 22 |
| CS1 | GPIO8 | 24 |
| CS2 | GPIO7 | 26 |
| BUSY | GPIO24 input | 18 |

SDA means MOSI, not I²C. No MISO. Physical selector stays at inspected 3 Ω. 0.47 Ω unvalidated; not enabled by software. Preserve fan wiring. Disconnect **all** adapter power, allow discharge, and inspect wiring/ribbon before confirming a new installation. Never switch resistor while powered, disconnect ribbon during refresh, or measure resistance while powered. Successful SPI writes alone do not prove either half displayed.

```sh
mkdir -p ~/.config/eink-codex
cp config/inspection.example.json ~/.config/eink-codex/inspection.json
```

Fill with actual observer, offset-aware timestamp and truthful checks. On this unchanged Pi, existing verified inspection was migrated; that personal confirmation is not bundled as a new-device default.

## Run

```sh
# Capture live telemetry/PNG; no panel access:
.venv/bin/eink-codex --windows 1
# Offline saved snapshot and mock panel:
.venv/bin/eink-codex --fixture validation/fixture.json --mock --windows 1
# Display access; stop other display owner first:
.venv/bin/eink-codex --hardware
# Install service from this checkout after environment and inspection exist:
sudo sh scripts/install-service.sh "$USER"
```

`--socket`, `--network-status`, `--interval` (minimum 5 seconds), `--windows` (0 continuous), `--state-dir`, `--inspection` configurable. Capture mode is default; imports/fixtures never access panel or start agents. `python -m codex_eink` equivalent to launcher.

Service installer stops/disables known Bitcoin/system display services, preserving their files. `eink-codex.service` runs own venv, enabled at boot, `Restart=no`. Only one panel owner. First image uses full baseline; subsequent changed images use exactly one partial waveform and complete RAM uploads to both controllers. No intermediate black/white clears, narrow RAM windows or automatic refresh retries. Same images skip activation. BUSY bounded at 20 seconds; panel update wall-clock budget 60 seconds; telemetry deadline 35 seconds. SIGINT/SIGTERM perform valid-state controller shutdown and release GPIO/SPI. Failed/stalled panel gets no further refresh. Cleanup does not disconnect physical power. Partial ghosting/lifetime not established; stop on abnormal heating/supply problems. Desktop resolution and game state unaffected.

```sh
systemctl status eink-codex --no-pager
journalctl -u eink-codex -o cat -n 20 --no-pager
sudo systemctl stop eink-codex
# Return to saved Bitcoin app:
sudo systemctl disable --now eink-codex
sudo systemctl enable --now eink-bitcoin
# Live setup viewer:
tmux attach -t pi-codex-setup
```

State defaults `~/.local/state/eink-codex`: PNG, 15,000-byte full frame, two row-split 7,500-byte planes, metadata, BUSY transitions, source fingerprints, preflight, events and latest telemetry. XDG_STATE_HOME/XDG_CONFIG_HOME respected. Logs contain status only, not prompts. Preview PNG is expected output, not a photo proving display appearance.

## Validation

```sh
.venv/bin/python -m unittest discover -v
.venv/bin/pip wheel --no-deps --no-build-isolation . -w dist
```

Forty-one tests cover pagination/deduplication, active/idle/error/unloaded/waiting/root/child states, unknown connection results, stale network data, resource cleanup, renderer/plane sizes, offline fixtures, no import activation, one mock full update, and no refresh retry after failure. Auth recovery tests cover expiry detection before truncation, real subprocess code parsing, single outstanding login, stale-code removal, retry cooldown, reload failure without another login, idle-agent reload gating, and preserving the agent panel. Usage tests cover window identification, missing data, zero versus unknown credits, remaining allowance, overdue resets, invalid numbers, expiry sorting and credit pagination. `scripts/verify-live.py` is an **optional real inference test**, not part of offline suite: starts one managed turn, sleeps 25 seconds once, checks active-to-idle transition, and saves evidence. It does not delegate agents. Requires authenticated account and uses quota.

See [executed results](validation/RESULTS.md). Software/BUSY completion does not certify a new whole-screen image; visual status remains INCONCLUSIVE without observation. No new electrical measurements or resistor comparison performed.
