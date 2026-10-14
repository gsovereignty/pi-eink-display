# Executed diagnostic results

Latest completed software validation: **2026-10-07 23:57:00 UTC+08:00**.
Hardware functional updates completed **2026-10-08 00:03:38 UTC+08:00**.
SPI setup and reboot completed. Post-reboot read-only preflight passed.
Nine actual 3 Ω refreshes executed: original smoke, white in an operator-interrupted
sequence, timing-change smoke, and six updates in the completed sequence. All
executed images confirmed correct by user. Whole WAKE retained after physical removal of all power, confirmed by user.

| Actually executed check | Result | Evidence |
|---|---|---|
| Fresh SSH over Bonjour IPv6 | PASS | Host `raspberrypi`, account `gareth`; persistent machine-specific socket restored after reboot. Direct IPv4 intermittently timed out. |
| Model / OS / kernel / Python | PASS | Pi 5 Model B Rev 1.0; Debian 13.5 trixie; 6.18.34+rpt-rpi-2712 ARM64; Python 3.13.5. |
| GPIO permissions / chip discovery | PASS | `gareth` in gpio/spi groups; discovered `/dev/gpiochip0`, `pinctrl-rp1`; gpiochip4 alias deduplicated. |
| GPIO7/8/17/24/25 ownership | PASS | Kernel CS pins unclaimed after SPI enablement; exclusive lgpio control claims succeeded during signal and smoke tests. |
| Python GPIO/SPI/image libraries | PASS | lgpio 0.2.2.0, spidev 3.6, Pillow 11.1.0 on Pi. Local Pillow 12.3.0. |
| Automated tests, local and Pi | PASS | 38 meaningful tests; [local log](software/unittest-local.log), [Pi log](software/unittest-pi.log). Fault injection and gate tests are simulated, including lines labeled hardware inside temporary test fixtures. |
| Actual original C++ image distribution | PASS | Both 7500-byte streams exactly match Python row-wise split; [Pi oracle](software/pi-reference/reference-oracle.json). |
| Original C++ init / full refresh / sleep trace | PASS | Recording shim executes pinned exact-panel methods; byte sequence matches port. No real hardware in oracle. |
| Mock smoke | PASS | Pi run `20261007-235659-d1df68`; simulated one full refresh plus power-off/sleep. |
| Mock functional 3 Ω | PASS | Pi run `20261007-235700-dd02f8`; white/black/halves/swapped/diagnostic/sleep-wake. |
| Mock functional 0.47 Ω | PASS | Pi run `20261007-235700-3eeebc`; same software sequence, simulated selector record only. |
| Dry-run pattern/buffer generation | PASS | Real PNG/bin artifacts generated; no GPIO/SPI transport opened. |
| Build wheel / installed-wheel mock smoke | PASS | `dist/hink_diagnostics-0.1.0-py3-none-any.whl`; isolated extraction/import/CLI mock smoke verified. |
| SPI device / configuration preflight | PASS | `/dev/spidev0.0` accessible after `spi0-0cs,no_miso` overlay and reboot; GPIO10/11 routed to SPI, GPIO9 unused. [Pi preflight](../runs/20261007-234634-cf784e/result.json). |
| BUSY input-only samples | INCONCLUSIVE | 20 samples all HIGH before reset; no outputs/reset/SPI writes. Does not establish stalled panel or polarity by itself. |
| Signal exercise, physical SPI | INCONCLUSIVE | Host successfully sent unselected SPI bytes and exercised both CS independently. No instrument readings; not proof of signal arrival at panel. |
| 3 Ω hardware smoke | PASS | [Actual run](../runs/20261007-235116-d800d6/result.json): exactly one refresh; BUSY HIGH then LOW in 1.599 s; power-on 0.073 s, power-off 0.094 s, normal sleep; no errors. User confirmed image success and no abnormal heat; Pi firmware throttled=0x0. Adapter voltage/current unmeasured. |
| 3 Ω functional updates | PASS | [Actual run](../runs/20261007-235812-9d1301/result.json): white, black, opposite halves, swapped halves, diagnostic and sleep/reset/wake image all confirmed correct; each BUSY refresh approximately 1.600 s. No errors; final normal sleep/cleanup. |
| 3 Ω retention / complete system | PASS | Normal display sleep, Pi shutdown, physical removal of all power, unchanged whole WAKE image confirmed by user. |
| 0.47 Ω hardware tests | NOT RUN | Execution explicitly blocked: no defensible adapter/panel RESE/booster evidence. |

## Hardware comparison

| Check | 3 Ω | 0.47 Ω |
|---|---|---|
| New whole-screen smoke image | PASS | NOT RUN |
| White / black | PASS | NOT RUN |
| Opposite halves / swapped halves | PASS | NOT RUN |
| Asymmetric corners / seam / orientation | PASS | NOT RUN |
| Sleep / reset-wake / further update | PASS | NOT RUN |
| Retention after physical power removal | PASS | NOT RUN |
| Complete system | PASS | NOT RUN |

Generated detailed [comparison JSON](../runs/comparison.json) and
[CSV](../runs/comparison.csv) exclude every mock/dry-run result.

Supply voltage, adapter current (average and switching peaks), panel/adapter
temperature and photographs are **unavailable**. Pi SoC temperature was 41.1 °C
from `vcgencmd`, and firmware reported `throttled=0x0`; these do not measure adapter
electrical limits. Visual completeness and orientation were user-confirmed;
diagnostic seam/ghosting confirmation is qualitative, with no contrast instrument.
No electrical readings invented.

Powered-off inspection and 3 Ω selector checks confirmed by user. SPI device and
exclusive CS ownership checks passed. Two software compatibility failures were
fixed before sending any refresh: missing spidev `open_path`, and dw-apb-ssi
rejecting `SPI_NO_CS`. Fallback validates live DT routing; no automatic refresh
retry occurred. Smoke and functional visual confirmations received. User requested no additional
inter-refresh delay; explicit `--spacing 0` used for revised smoke/functional runs
with identical revision/configuration. Default remains conservative 180 s.
Original white-only functional run was interrupted during spacing by operator
for this requested timing change; its FAIL status records KeyboardInterrupt,
not an established hardware defect. No failed-refresh retry occurred.
0.47 Ω additionally needs adapter circuitry and exact-panel validation evidence.

Prior Pi SPI configuration blocker resolved. No current hardware defect established.
Transport, wiring, driver/batch compatibility, adapter power circuitry and panel
remain untested hypotheses. Complete 3 Ω system works under tested conditions. No present failure to rank.
Any future defects should be isolated by measured supply/signal checks and known-good
substitution before blaming adapter. 0.47 Ω needs circuit/RESE/booster evidence
before execution. Instrument signal capture remains available if defects appear. Failed update would not prove adapter defective without
known-good substitute hardware.

## Subsequent refresh-rate test

Benchmark revision passed 42 automated tests on development host and Pi, plus
original C++ oracle and installed-wheel mock benchmark. One 4 MHz smoke was
visually confirmed correct before the three-update live burst.
Run `20261008-002145-132dd6` measured **0.6094 Hz / 1.6411 s per full frame**;
BUSY 1.5992–1.6003 s, upload approximately 0.037 s. Normal final sleep and cleanup,
no errors. All-three-image visual observation pending. This is short-burst
throughput, not a continuous operation or lifetime rating. See
[benchmark report](../docs/REFRESH_RATE.md).

## Desktop snapshot

Live Wayland/labwc desktop captured at 1680 × 1050 and fitted without cropping
or changing desktop resolution. Run `20261008-003355-fa3b45` sent one full
400 × 300 monochrome framebuffer; BUSY 1.598 s, no errors, normal power-off/sleep.
Whole-screen image and no heat/supply trouble confirmed by user: PASS. Conversion and CLI tests bring the suite to 46
passing tests on development host and Pi. See [desktop guide](../docs/DESKTOP.md).

## Automatic top monitor

Installed and enabled `eink-top.service`, ordinary account `gareth`. Real procps
`top` samples CPU/memory/processes each second; rendered rows use time-weighted
preceding ten-second averages. Sampling continues while the display refreshes.
Reboot startup PASS at 2026-10-08 09:30:59 (UTC+08:00), with new boot ID, matching
service/application PID and successful hardware updates without manual startup.
Post-reboot refresh starts measured 10.020–10.079 s apart; BUSY 1.601–1.646 s.
The initial 9.796-second startup window prompted a rolling-history correction:
every published window now requires at least ten seconds of samples. Corrected
software passed 57 tests on Mac and Pi and live updates with 10.000-second windows.
The built wheel passed isolated import/render/packing validation.

Current monitor whole-screen readability, advancing counter and no abnormal heating:
**PASS**, user confirmed “it's working” after screen-verification request.
No electrical or temperature readings were supplied.
Electrical measurements remain unavailable. Configuration, versions, raw top,
expected PNGs, framebuffer/controller streams and JSON/CSV histories archived in
`runs/top-monitor-before-reboot`, `runs/top-monitor-after-reboot` and
`runs/top-monitor-rolling-window`. See `evidence/software/top-validation.json`
and [monitor setup/operation guide](../docs/TOP_MONITOR.md).

## Changed-line partial monitor, 2026-10-08

User requested removal of white full-screen flash between TOP updates. Ported
pinned exact-panel partial LUT and update sequence; no guessed waveform.
62 automated tests PASS on Mac and Pi; original full-driver C++ oracle PASS.
Live service performed one initial full baseline followed by partial changed-band
updates. First partial update: six bands, total BUSY 2.516 s; each update retains
preceding ten-second averages. No periodic full clearing is configured.
Physical no-flash/readability confirmation PENDING USER OBSERVATION.
See `runs/top-partial-validation` and `evidence/software/partial-validation.json`.

## Resource dashboard, 2026-10-08

Installed fixed dashboard as the default of enabled `eink-top.service`: CPU/core
bars, Pi SoC temperature, RAM/swap, root free disk space, actual five-minute CPU/RAM
history, ten-second network/disk rates, three busiest processes, uptime, WiFi signal
and firmware flags. 68 tests PASS on Mac and Pi; wheel render and original reference
oracle PASS. Two real capture-only windows executed before service restart.
Live dashboard baseline and changed-band updates completed successfully, ten-second
averages preserved; first start interval 10.051 s and partial BUSY total 2.935 s.
No post-startup full clear configured. Physical dashboard readability/no-flash
confirmation PENDING USER OBSERVATION. Expected images, buffers, version and metrics
saved in `runs/dashboard-hardware-validation`; synthetic layout example is separately
labeled in `runs/dashboard-layout-preview`. See [dashboard guide](../docs/DASHBOARD.md).

## Black/white before each dashboard update, 2026-10-08

User requested full black and white before every update, superseding partial-only
mode. Default service now executes black/full refresh, white/full refresh, then
dashboard/full refresh, bounded BUSY and normal power-off after each stage.
71 tests PASS on Mac and Pi, including exact frame sequence and no subsequent
white/dashboard writes after a failed black stage. First live cycle completed
in 5.425 s; BUSY durations 1.601/1.602/1.600 s. Ten-second sampling remains parallel.
Logs, expected clearing PNGs and latest dashboard buffers saved in
`runs/dashboard-black-white-validation`; `clear-validation.json` records timing.
Visible black/white/dashboard sequence has not yet been manually confirmed.

## Single full dashboard refresh, 2026-10-08

Latest user request supersedes the black/white clearing cycle. Default now sends
only the dashboard image and one full-refresh sequence per update, then normal
power-off. No separate clearing frames. 73 tests PASS on Mac and Pi, including
one refresh per repeated/initial image and no further commands after a stall.
Live service active in `full` mode; two updates completed, BUSY approximately
1.602 s. Full waveform can still flash internally; visible transitions must not
be confused with multiple host refreshes. Version, timings and expected image
archived in `runs/dashboard-single-full-validation` and
`evidence/software/single-full-validation.json`.

## Partial dashboard restored, 2026-10-08

User identified black as a transient full-waveform flash and requested partial
refresh again. Default is now `--clear-cycle off`: initial full baseline only,
then changed-band updates. Service active; two live partial updates completed,
about 10.06 s apart with total BUSY about 3.355 s. 73 tests PASS on Mac and Pi.
Saved `runs/dashboard-partial-restored` and
`evidence/software/partial-restored-validation.json`. No additional full clears
are scheduled. Visible partial-update behavior awaits user observation.

## Dashboard network details, 2026-10-08

Added actual IPv4/IPv6 address rows, rolling minute RX/TX byte rates and kernel
cumulative RX/TX since boot/interface creation. Cumulative values persist across
service restarts. Warmup labels actual observed window; rates are scaled to B/min.
77 tests PASS on Mac and Pi. Actual capture-only preview and live changed-band
update executed; service enabled/active, default partial behavior preserved.
Real addresses included 192.168.50.191 and fe80::e6ee:582c:c8ee:c230 on wlan0.
PNG inspected for complete addresses and readable lower panels. Physical layout
confirmation remains pending. Evidence: `runs/dashboard-network-preview`,
`runs/dashboard-network-hardware`, `evidence/software/network-validation.json`.

## Snow correction, 2026-10-08

Camera captured horizontal speckled bands across both halves. Restoring full RAM
windows and reducing activation to one partial update reduced flashing but did
not eliminate snow. Second correction uploads both complete 7500-byte controller
images, restores full RAM windows and activates the unchanged partial waveform
once. No additional black/white images, voltage changes or guessed LUTs.
79 automated tests PASS on Mac and Pi; actual pinned C++ partial scan/activation
oracle PASS. Live partial BUSY about 0.419 s, ten-second cadence retained.
Gareth's observation: “it seems to be ok now”. Reported resolved, no endurance claim.
State/version/expected image in `runs/snow-full-buffer-validation`, detailed result
in `evidence/software/snow-validation.json`. Camera clips in `runs/camera-inspection`
record baseline and first failed correction; second-correction recording had no
screen in view and is not visual proof. Final evidence is user's direct observation.
