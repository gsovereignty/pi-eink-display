# Standalone applications

Dashboard extracted to `../eink-dashboard`; reusable exact-panel driver and pin/setup documentation extracted to `../eink-driver`. Both provide source archives and Python wheels in their respective `dist/` directories. Neither imports this diagnostics project.

- [Dashboard setup and commands](../../eink-dashboard/README.md)
- [Driver, pin connections and Pi 5 setup](../../eink-driver/README.md)
- [Executed packaging checks](../../eink-dashboard/VALIDATION.md)

Pi installs reside under `/home/gareth/git/hardware/eink-dashboard` and `/home/gareth/git/hardware/eink-driver`. Installed packages live in dashboard `.venv`; new `eink-dashboard.service` runs from user home and starts at boot. Prior `eink-top.service` disabled; original diagnostics and unit preserved.

Physical settings unchanged: 3 Ω, same wiring, fan preserved. New service completed full baseline and partial updates; fresh visual verification after extraction remains unrecorded. Electrical measurements unavailable; 0.47 Ω not tested.
