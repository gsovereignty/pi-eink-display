#!/bin/bash
set -euo pipefail
exec > >(tee -a /home/gareth/.local/state/pi-codex-setup.log) 2>&1
nmcli -f NAME,TYPE,DEVICE connection show --active
mkdir -p /home/gareth/.local/share/codex/0.161.0 /home/gareth/.local/bin
curl --fail --location --retry 2 --connect-timeout 10 --max-time 240 https://github.com/openai/codex/releases/download/rust-v0.161.0/codex-package-aarch64-unknown-linux-musl.tar.gz -o /tmp/codex-package-0.161.0.tar.gz
printf '%s\n' '3c02e2ae34be0d06e62557e98fc5c0a783bec5a2fed406fe00e565803bf84ee8  /tmp/codex-package-0.161.0.tar.gz' | sha256sum -c -
tar -tzf /tmp/codex-package-0.161.0.tar.gz | head -15 || true
tar -xzf /tmp/codex-package-0.161.0.tar.gz -C /home/gareth/.local/share/codex/0.161.0
find /home/gareth/.local/share/codex/0.161.0 -maxdepth 3 -name codex -type f
ln -sfn /home/gareth/.local/share/codex/0.161.0/bin/codex /home/gareth/.local/bin/codex
/home/gareth/.local/bin/codex --version
