# Packaging validation

Executed on Mac and connected Pi: dashboard 36 tests PASS on each; driver 41 tests PASS on each. Compiled exact-source full and partial C++ reference checks PASS on each. Wheels built on Pi without dependency downloads; installed into dashboard venv. Imports resolved from installed site-packages while working directory was `/tmp`, independently of diagnostics source.

Driver dry-run and mock PASS on Pi. Dashboard capture-only generated expected PNG; two-window mock completed baseline and partial update without hardware access. Initial read-only preflight reported occupied GPIO lines because old dashboard service was still running; after graceful stop, new service preflight passed all four checks.

Standalone hardware service started 2026-10-08 13:13:39 +08:00. Initial full refresh completed with active BUSY, approximately 1.60 s. Subsequent partial update completed with active BUSY, approximately 0.42 s. Logs, runtime source fingerprints, expected PNG and metrics in `validation/pi/`; these are snapshots, not a claim of visual success after repackaging. Fresh visual confirmation NOT RUN; whole-display visual status INCONCLUSIVE. Existing prior user confirmation of working dashboard remains historical evidence.

`eink-dashboard.service` enabled and active; old `eink-top.service` disabled and inactive. Original source/unit preserved. Boot enablement checked; no new Pi reboot performed. No new supply/current measurements, no 0.47 Ω execution, no endurance tests.
