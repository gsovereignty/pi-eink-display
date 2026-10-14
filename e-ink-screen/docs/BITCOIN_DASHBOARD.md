# Bitcoin dashboard

Saved as independent application `../eink-bitcoin`, version 0.1.0. Package `bitcoin_eink`, command `eink-bitcoin`, own venv and inspection config, separate reusable `eink-driver` dependency. App/driver wheels and source archive under its `dist/` directory.

[Independent app source, pin connections and setup](../../eink-bitcoin/README.md)

[Executed extraction validation](../../eink-bitcoin/validation/RESULTS.md)

Pi service `eink-bitcoin.service` active and boot-enabled, now launching `/home/gareth/git/hardware/eink-bitcoin/.venv/bin/python -m bitcoin_eink` from user home. Existing integrated code preserved for rollback; no dependency on it in new app.
