# Unexpected Pi restarts: power supply replacement

Recorded 2026-10-08T12:48:59.828+08:00.

Gareth reported repeated unsolicited shutdowns/restarts, then confirmed: “I changed
power supply and its ok now”. Replacement resolved the reported symptom. This
strongly implicates the previous supply/cable path; it does not isolate a failed
component or prove a particular electrical mechanism.

## Evidence actually collected

* Distinct boot IDs `072e101e-2280-4e56-83d4-305626cbe42c` and
  `1a9c1cf5-9ae7-4e53-862c-1ebe879f9e73` proved actual reboots.
* Old journal storage was explicitly volatile in
  `/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf`. Earlier boot
  shutdown logs were unavailable; their cause cannot be reconstructed from them.
* Current-boot firmware flag `throttled=0x0`; SoC initially 37.8°C, later 39.5°C.
  Clean current-boot flags cannot rule out earlier transients before reboot.
* PMIC ADC snapshot: EXT5V 5.079940 V, 3V3_SYS 3.304465 V. These are firmware
  snapshots, not scope captures, panel measurements or measured switching peaks.
* Negotiated supply limit 3000 mA, including after reported replacement. Supply
  rating alone therefore does not establish that the old source was adequate.
* System manager runtime watchdog configured at one minute. No retained evidence
  established that watchdog triggered. No power-button shutdown event was found
  in the inspected current logs. Display service remained active.

## Logging change installed

Added `/etc/systemd/journald.conf.d/99-pi-shutdown-diagnosis.conf`:

```ini
[Journal]
Storage=persistent
SystemMaxUse=64M
RuntimeMaxUse=16M
SyncIntervalSec=5s
```

Restarted journald and flushed current journal to persistent storage. Verified
effective override and 16 MiB journal usage. This survives boots; an abrupt power
cut may still lose the newest unsynced messages. No reboot, display-mode change,
fan rewiring, EEPROM update or watchdog change was made during diagnosis.

Persistent tmux viewer on Pi: `pi-shutdown-diagnosis`, window `journal`.
Current boot archived locally in `runs/shutdown-diagnosis/current-boot.log`.

If recurrence happens, inspect `journalctl --list-boots`, `journalctl -b -1 -e`,
current firmware flags and chosen-power/reset information before resetting again.
Distinguish clean shutdown, abrupt log termination, watchdog evidence and network
loss. Preserve wiring; use known-good supply/cable comparison before blaming
Pi, e-paper adapter or panel.
