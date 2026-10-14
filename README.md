# Pi E-Ink Display

Applications and shared driver for Raspberry Pi 5 and the HINK-E042A03-A1
400 × 300 dual-controller monochrome e-paper panel.

| Directory | Purpose |
| --- | --- |
| [eink-codex](eink-codex/) | Codex agent counts, account usage, and automatic device-login prompts |
| [eink-dashboard](eink-dashboard/) | CPU, memory, disk, network, and process dashboard |
| [eink-bitcoin](eink-bitcoin/) | Bitcoin price, blocks, fees, mempool, and difficulty |
| [eink-driver](eink-driver/) | Shared panel driver, wiring guide, and controller diagnostics |
| [e-ink-screen](e-ink-screen/) | Original diagnostics, desktop capture, and Pi setup scripts |

The Norns game mirror has been removed. Only one application may own the panel
at a time. Stop the current display service before starting another hardware app.

## Install from this repository

Follow [Pi hardware setup](e-ink-screen/SETUP_NEW_PI.md) and
[driver wiring/inspection instructions](eink-driver/README.md) first.
Install the documented OS GPIO/SPI packages and Python venv support. From the
chosen app directory (for example `eink-codex`):

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install ../eink-driver .
mkdir -p ~/.config/eink-codex
cp config/inspection.example.json ~/.config/eink-codex/inspection.json
# Fill inspection.json with your actual powered-off hardware inspection.
sudo sh scripts/install-service.sh "$USER"
```

Use the matching configuration directory for each application. Codex also needs
an installed Codex CLI and managed daemon; see its README and the setup scripts.
Existing SSH host aliases/collectors are provisioned separately. Do not copy
another machine's credentials. Network setup scripts document the original
Pi deployment and may require path/account changes on another machine.

Tests run from each project directory using `python -m unittest discover -v`.
Build wheels locally with `python -m pip wheel --no-deps . -w dist` after installing
build dependencies. Earlier project documents describe deployment archives and
runtime evidence; generated archives, machine snapshots, login-code screenshots,
logs, credentials, and personal inspection confirmations are intentionally not
versioned here. Source code, tests, example configuration, upstream driver sources,
licenses, and written validation reports are included.

## License

GPL-3.0; upstream notices and source attribution remain in the driver and
diagnostics directories.
