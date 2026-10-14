#!/bin/bash
set -euo pipefail
exec > >(tee -a /home/gareth/.local/state/pi-codex-setup.log) 2>&1
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends wireguard-tools curl ca-certificates
curl --fail --location --max-time 45 https://install.zerotier.com/ -o /tmp/install-zerotier.sh
bash /tmp/install-zerotier.sh
systemctl enable --now zerotier-one
zerotier-cli join 8d1c312afae039bc
zerotier-cli set 8d1c312afae039bc allowDefault=0
zerotier-cli set 8d1c312afae039bc allowDNS=0
zerotier-cli info
zerotier-cli listnetworks
