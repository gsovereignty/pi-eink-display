# Independent application validation

14 app tests PASS on Mac; 14 PASS on Pi. Separate app and driver wheels installed in new `/home/gareth/git/hardware/eink-bitcoin/.venv`. Imports resolved from its site-packages while working directory was `/tmp`; `epaper_dashboard` module absent from this environment. Live API capture and mock refresh PASS without panel access.

Boot service migrated to new venv, `python -m bitcoin_eink`, and own `~/.config/eink-bitcoin/inspection.json`; previous integrated code/unit backup preserved. Service active/enabled; no reboot performed. Existing inspected configuration copied only for same unchanged physical Pi/panel, not supplied as new-hardware default.

New independent runtime completed full baseline (approximately 1.59 s BUSY) and subsequent partial update (approximately 0.42 s BUSY), active BUSY observed, no API errors. Runtime fingerprint matches saved source. Software sequence PASS; new whole-screen visual observation NOT RUN, hardware visual status INCONCLUSIVE. No new electrical measurements, 0.47 Ω tests or endurance runs. Snapshot artifacts here are historical evidence.

Existing independent driver already validated separately; driver source unchanged during this extraction. No new driver-suite run claimed here.
