#!/bin/sh
set -eu
# Run on the Pi via sudo. No GPIO writes and no implicit reboot.
test "$(id -u)" = 0 || { echo 'Run via sudo'; exit 1; }
config=/boot/firmware/config.txt
if grep -Eq '^[[:space:]]*dtparam=spi=on|^[[:space:]]*dtoverlay=spi0-(1cs|2cs|cs)' "$config"; then
    echo 'Conflicting SPI configuration; inspect config.txt before changing it.'
    exit 1
fi
if ! grep -q '^dtoverlay=spi0-0cs,no_miso$' "$config"; then
    backup="$config.epaper-$(date +%s).bak"
    cp -p "$config" "$backup"
    printf '\n[all]\n# HINK dual manual CS; leave GPIO9 and fan connections alone\ndtoverlay=spi0-0cs,no_miso\n' >> "$config"
    echo "Saved backup: $backup"
fi
apt-get update
apt-get install --no-install-recommends -y python3-lgpio python3-spidev python3-pil gpiod tmux
echo 'Setup complete. Reboot required before hardware preflight. No refresh sent.'
