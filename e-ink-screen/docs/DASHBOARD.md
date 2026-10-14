# Raspberry Pi e-paper resource dashboard

The existing enabled `eink-top.service` now defaults to a fixed 400 × 300 dashboard.
It retains real `top` sampling, ten-second weighted averages, independent chip
selects and bounded BUSY waits. One full refresh establishes the baseline after
startup. Subsequent updates detect changed rows, upload both complete controller buffers,
restore full RAM windows and use one exact-panel partial activation; no separate black/white clearing images or periodic full refreshes.
Sampling continues during refresh. Partial behavior and ghosting need visual checks.

## Layout and meaning

* CPU: busy percentage excluding idle and I/O wait, averaged over the previous ten
  seconds. Four per-core bars use `/proc/stat` deltas; guest times are not counted
  twice. Temperature is the latest Pi SoC thermal reading, not adapter temperature.
* RAM: ten-second mean used/total GiB, usage bar and swap MiB from `top`.
  Disk free space is the latest available space on `/`, in GiB.
* History: CPU and RAM percentages over the latest five minutes, fixed 0–100% axes.
  History starts empty and fills from the right using actual sample timestamps.
  It is bounded, resets when the service restarts, and never fabricates old data.
* IP addresses: non-loopback IPv4 and IPv6 addresses from `ip -j address show`,
  refreshed every ten seconds. Two full-width rows show complete addresses.
  More than two addresses rotate in pairs every three updates; interface names
  identify link-local IPv6 scope. No address is guessed from hostname resolution.
* Activity: RX/TX throughput in bytes per minute, time-weighted over the preceding
  sixty seconds of observed counter deltas. Before sixty seconds are available,
  the panel labels the shorter actual window and scales its measured rate to
  bytes/minute. This is a throughput rate, not a claim that a full minute elapsed.
  Activity follows the first interface on the currently displayed address page;
  without addresses it prefers wlan0, then the first non-loopback interface.
* Cumulative traffic: latest kernel RX/TX byte counters, labeled `Boot`. Normal Pi
  reboot resets these; restarting only the dashboard service preserves them.
  Interface recreation/driver counter resets also reset their counters. They are
  interface bytes, including background/network overhead, not application payload.
  Counter resets never generate fake throughput spikes. K/M/G use binary units.
* Disk R/W: ten-second read/write bytes per second, shown beneath RAM/storage.
  Root backing block-device counters avoid summing partitions and their parent.
* Processes: three current processes with highest ten-second average CPU usage,
  followed by resident MiB. Process CPU 100% means one core; names may be truncated.
* Footer: current uptime, wlan0 signal in dBm, firmware throttling flags and update
  counter. `Flags OK` means `vcgencmd get_throttled` returned zero; it is not an
  electrical measurement. `WARN 0x...` includes current or historical flags.

Absent sensors, inaccessible firmware flags, unavailable devices and counter resets
show `--`; they are not reported as zero. Root-device mapping uses `/sys/dev/block`.
Complex device-mapper/RAID setups report that mapped root device, not guessed physical
members. Metric collection uses ordinary service account permissions and changes no
network, fan, voltage, storage or desktop-resolution configuration.

Sources: [Linux /proc documentation](https://docs.kernel.org/filesystems/proc.html),
[Linux disk I/O counters](https://docs.kernel.org/admin-guide/iostats.html),
[Raspberry Pi vcgencmd documentation](https://www.raspberrypi.com/documentation/computers/os.html#vcgencmd).

## Reproduce and operate

Complete [new-Pi setup](../SETUP_NEW_PI.md) and
[service setup](TOP_MONITOR.md), including powered-off wiring inspection. No new
Python dependency is needed. Existing boot service automatically selects dashboard.

```sh
python3 -m unittest discover -v
python3 -m hink_diag.top_display --layout dashboard --windows 2 --state-dir runs/dashboard-preview
sudo sh scripts/install_top_service.sh gareth
systemctl status eink-top.service --no-pager
journalctl -fu eink-top.service
```

The preview samples actual Linux metrics, saves expected PNGs and buffers, and
opens no GPIO/SPI. The old table remains available with `--layout table`.
Stop the service before manually invoking any hardware display command:

```sh
sudo systemctl stop eink-top.service
python3 -m hink_diag.top_display --hardware --layout table --windows 2
sudo systemctl start eink-top.service
```

State remains in `~/.local/state/eink-top`, including code/configuration manifest,
raw top, latest metrics and expected PNG, full/controller buffers and bounded update
history. Physical readability, ghosting and no-flash behavior need visual observation;
SPI/BUSY alone cannot establish them. See executed results in `evidence/RESULTS.md`.

## Refresh mode

`--clear-cycle off` is the default, including for the existing boot service.
It uses one partial activation after one full baseline. An identical image
triggers no refresh. A failed update stops execution without retries.

`--clear-cycle full` explicitly selects one full dashboard refresh per update;
its waveform flashes black. `--clear-cycle black-white` selects the older
three-refresh sequence. Neither is the current default. Stop the service before
any manual hardware command. Capture-only preview opens no display transport:

```sh
python3 -m hink_diag.top_display --clear-cycle off --windows 2 --state-dir runs/dashboard-preview
```

## Network execution evidence

Automated tests cover IPv4/IPv6 extraction, loopback exclusion, sixty-second
window clipping, rate warmup, interface/counter resets and preserving latest
cumulative counters rather than averaging them. Actual Pi addresses and kernel
traffic counters were inspected before deployment. Software logs and image
previews are saved separately from physical screen observations.

## Snow artifact investigation

Camera footage showed dense horizontal speckling during the initial band-by-band
implementation. First correction restored complete RAM windows and consolidated
activation, reducing flashes but leaving snow in recorded footage. Current version
also removes narrow RAM writes: both complete 7500-byte controller buffers are
uploaded before one partial activation. Full data upload is not a full waveform;
partial LUT and update byte 0x04 remain unchanged. Identical frames still skip.
Gareth reported the second correction working: “it seems to be ok now”.
The first correction alone failed visibly. No endurance validation is claimed. One full baseline is required after restart.

`python3 scripts/partial_reference_oracle.py` executes the pinned Arduino C++ driver
and compares partial initialization and full scan/activation/power-off commands.
It records the established deferred power-on ordering difference explicitly.
Tests verify complete seam-correct buffers, restored windows, a single activation
and no subsequent refresh after upload/BUSY failure.
