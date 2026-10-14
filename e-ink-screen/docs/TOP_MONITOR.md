# Automatic e-paper process monitor

Current default is the [resource dashboard](DASHBOARD.md), with changed-band partial updates
after one initial full baseline refresh. Historical partial-update behavior below is available
with `--clear-cycle off`. Use `--layout table`
for the original thirteen-row TOP display described below.

The Pi runs the real `top` command continuously and displays readable CPU,
memory and process rows on the 400 × 300 panel. Approximately ten one-second samples feed each
display update. Startup is independent of the graphical desktop or SSH login.

## What the numbers mean

CPU percentages and memory values (including per-process CPU, memory percentage
and resident MiB) are time-weighted averages over the preceding **10.000 seconds**.
The first `top` frame is discarded because its CPU percentages reflect uptime.
Small scheduling overruns are handled by clipping the oldest sampled interval.
These are sampled averages, not continuous instrumentation. A process that was
absent for part of the window contributes zero during that portion. Only processes
still present at the latest sample are shown; PID plus kernel start time avoids
merging reused PIDs. The rows are sorted by average CPU, then resident memory.

CPU 100% means one fully occupied core; a multithreaded process can exceed 100%.
The system CPU summary is normalized across the Pi's cores. Load averages retain
the standard kernel 1/5/15-minute meaning and are the latest values, as is task
count. They are explicitly separate from the 10-second CPU/memory averages.

The underlying command is:

```sh
/usr/bin/top -b -d 1 -w 512 -E m -e m -o %CPU
```

It uses `LC_ALL=C`, `TZ=Asia/Shanghai`, and an isolated empty top configuration
directory. Your existing personal `top` settings remain unchanged. Sampling runs
in a separate thread while the panel updates. Linux scheduling introduces small
cadence jitter: actual refresh starts were approximately 10.06 seconds apart,
not 10 seconds plus the panel's ~1.6-second waveform duration.

## Installed service

| Setting | Value on this Pi |
|---|---|
| Unit | `eink-top.service` |
| Unit file | `/etc/systemd/system/eink-top.service` |
| Boot target | `multi-user.target` |
| Account | `gareth`, supplemental `gpio` and `spi` groups |
| Source directory | `/home/gareth/git/hardware/e-ink-screen` |
| Command | `/usr/bin/python3 -m hink_diag.top_display --hardware` with explicit inspection/state paths |
| State directory | `/home/gareth/.local/state/eink-top` |
| Resistor | Physically confirmed 3 Ω; software cannot change or verify selector |
| Transport | Exact dual-controller driver, mode 0, MSB first, 4 MHz |
| Failure policy | Stop on error; `Restart=no`, no automatic refresh retries |

The program permits up to 30 seconds for the SPI device to appear at boot, then
checks model/libraries/GPIO ownership and the existing dated physical inspection.
It initializes once, retains independent chip selects, respects bounded BUSY
waits, and turns the booster off after each successful update. Busy-wait history
and interval history are bounded. The monitor now uses the exact pinned driver's partial LUT and `22 04; 20`
update after the initial full baseline. No voltage/booster sweep, OTP programming
or writes during BUSY are introduced.

## Reproduce on a new Pi

Complete [SETUP_NEW_PI.md](../SETUP_NEW_PI.md), including the actual powered-off
wiring/ribbon inspection, fan preservation and 3 Ω selector confirmation. Install
`procps` and `fonts-dejavu-core` if `top` and DejaVu Sans Mono are missing.
Run tests and a capture-only preview before enabling hardware:

```sh
cd /home/gareth/git/hardware/e-ink-screen
python3 -m unittest discover -v
python3 -m hink_diag.top_display --windows 2 --state-dir runs/top-preview
```

The preview runs actual Linux `top`, saves two averaged images, and opens no
GPIO/SPI transport. Optional `--mock` exercises the driver with fake GPIO/SPI.
The application requires Linux/procps for real sampling; its parsing, averaging,
rendering and queue tests also run on the development Mac.

Install and enable the boot service, substituting the new account as needed:

```sh
sudo sh scripts/install_top_service.sh gareth
```

The installer resolves the project/account home directories, validates the unit
with `systemd-analyze verify`, backs up an existing unit if present, and enables
and starts the service. It does not enable SSH, change HDMI resolution, alter fan
wiring or install passwordless sudo. Verify the panel visually and reboot once
to confirm boot startup.

## Operate and inspect

```sh
systemctl status eink-top.service --no-pager
systemctl is-enabled eink-top.service
journalctl -fu eink-top.service
sudo systemctl stop eink-top.service
sudo systemctl start eink-top.service
sudo systemctl disable --now eink-top.service
```

Do not launch another hardware display command while this service owns GPIO/SPI.
Stop it first. A graceful stop between updates performs normal sleep and releases
resources. If interrupted during an uncertain/stalled controller state, cleanup
deasserts selects and releases resources without further controller commands;
GPIO cleanup does not physically remove adapter power. Diagnose errors before
restarting. Stop and disconnect power for abnormal heating or supply trouble.

The first averaged image appears about 12 seconds after initialization. Counter
and local time advance with subsequent updates; all timestamps include UTC+08:00.
The display is monochrome with up to thirteen process rows, not a screenshot of
a terminal window. It remains readable without a desktop session.

The state directory holds `startup.json` (PID, boot ID, code hashes/configuration),
`preflight.json`, `latest.json`, `latest.png`, the full 15,000-byte framebuffer,
two 7,500-byte controller streams, and `latest-top.txt` (actual final raw sample).
`history.json` retains at most 120 update timing records. These files are replaced,
not appended indefinitely. `stopped.json` records normal application cleanup;
use systemd state/current boot ID to determine whether a process is alive.

Persistent remote viewer: Pi tmux session **`e-ink-top`**, window `service-log`.
After a reboot the service starts independently; recreate the tmux viewer if
needed. SSH details are in [SETUP_NEW_PI.md](../SETUP_NEW_PI.md).

## Verification

Current suite has **68 passing automated tests** on development host and Pi,
including real top format, weighted averages, exact-window clipping, PID reuse,
process exit, framebuffer packing, initial-frame discard, short startup windows and sampler failures.
The original C++ oracle still matches the panel's init/full-refresh/sleep trace.
Two actual Pi sample windows passed through mocked GPIO/SPI before installation.

Before reboot, nine live updates completed with BUSY 1.6006–1.6014 seconds;
refresh-start intervals 10.0567–10.0697 seconds. Average windows were 10.000 seconds.
Pi SoC temperature was 39.5 °C and firmware flags `throttled=0x0`. These do not
measure panel/adapter temperature or supply current/voltage. See archived
[pre-reboot state](../runs/top-monitor-before-reboot/startup.json).

Reboot startup verified at 2026-10-08 09:30:59 (UTC+08:00): new boot ID,
enabled/active service and successful hardware updates without manual startup.
The first startup window exposed a 9.80-second sampling span; the sampler now
retains rolling history and waits until a full 10 seconds exist before publishing.
Final visible operation confirmed by Gareth: “it's working”. Monitor PASS. Continuous service operation is user-requested; the short tests
do not establish panel lifetime or adapter component ratings.

## Changed-line updates (2026-10-08)

After one full refresh at service startup, the monitor compares packed pixel rows
against its last successful image. It groups changed rows into full-width bands
(bridging at most three blank glyph rows), uses the dirty bands to detect change, uploads both complete 200-pixel
controller halves and invokes one exact-panel partial waveform after restoring
the full RAM windows. Identical images
produce no RAM writes or refresh. The baseline advances only after all bands succeed.
Both controllers receive matching Y windows, including changes crossing the seam.
Booster power is removed after the complete update; no automatic full clears or
full-refresh retries occur between updates. A restart requires one full baseline.

The source is the pinned `GxEPD2_2IC_420_A03` version 1.4.8, whose header explicitly
reports partial support. Its 30-byte `LUTDefault_part` and update byte `0x04` are
ported unchanged. Existing full diagnostics retain their original full waveform.
Partial mode can accumulate ghosting; report image defects rather than assuming
hardware health from SPI/BUSY. Physical no-flash confirmation remains pending.

Tests cover exact source LUT bytes, changed-row grouping, unchanged-frame skip,
7500-byte half layout cropped to bands, seam pixels, select swapping, full-baseline
requirement and no retry/cleanup command after a stalled partial update.
