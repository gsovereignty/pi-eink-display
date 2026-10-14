# Pi networking and Codex installation

Verified 2026-10-08T16:36:09+08:00, Asia/Shanghai. Pi `gareth@raspberrypi.local`, Raspberry Pi 5, Debian 13 arm64. LAN IPv4 observed `192.168.50.191`; may change. SSH control socket `~/.ssh/raspberrypi`. Persistent viewer on Pi: `tmux attach -t pi-codex-setup`, including `codex-dashboard` journal window.

## Actual installation status

| Requirement | Result | Evidence |
|---|---|---|
| ZeroTier installed and boot enabled | PASS | zerotier-one 1.16.2, service enabled/active |
| Joined Nostrocket request | PASS | network 8d1c312afae039bc configured on node 712e31e078 |
| Authorized Nostrocket connectivity | PASS | OK; 10.46.107.199/24; peer 10.46.107.74 replied to 3/3 pings over ztu7tnce2g |
| WireGuard selected destinations | PASS | real handshake; OpenAI route through ivpn-openai; exit 185.135.77.63 |
| Normal LAN/default path preserved | PASS | 1.1.1.1 via wlan0 gateway 192.168.50.1; SSH remains live |
| Codex installed after WireGuard | PASS | native arm64-musl 0.161.0 installed after VPN verification |
| Codex account and actual inference | PASS | login status authenticated; actual first inference returned PI_CODEX_READY |
| Managed daemon and boot unit | PASS | daemon active; unit enabled; controlled stop/start succeeded |
| E-ink status app | PASS software | independent eink-codex, active/enabled, real active-to-idle count tested |
| New physical screen appearance | INCONCLUSIVE | BUSY/full/partial sequences completed; no new manual visual observation |
| Fresh reboot validation | NOT RUN | boot units enabled, verified; no reboot requested for app migration |

Requested installation and dashboard setup complete. User authorized Pi node; membership rechecked as OK with assigned IPv4 and IPv6. Pi reached authorized Mac peer 10.46.107.74 with 3/3 replies, zero loss; `ip route get` proved traffic used ZeroTier interface ztu7tnce2g, source 10.46.107.199. Dashboard live telemetry now includes ZT OK. Fresh boot and new physical screen appearance remain unverified as listed above.

Historical setup initially returned ACCESS_DENIED. No usable controller credentials were available to automation; user later authorized node. Historical fixtures/previews retain that original state and are not current-status evidence.

## ZeroTier

Official installer `https://install.zerotier.com` installed daemon 1.16.2. Configured network:

```sh
sudo zerotier-cli join 8d1c312afae039bc
sudo zerotier-cli set 8d1c312afae039bc allowDefault=0
sudo zerotier-cli set 8d1c312afae039bc allowDNS=0
sudo zerotier-cli -j listnetworks
```

Pi identity **712e31e078** is now authorized in network controller. Assigned IPv4 **10.46.107.199/24**, IPv6 **fd8d:1c31:2afa:e039:bc99:9371:2e31:e078/88**. Do not fabricate another node identity, claim joined request is connectivity, or broaden default-route/DNS permissions to fix ACCESS_DENIED. Connection is proved only when membership is OK, assigned address present and authorized peer is reachable. Identity private key stays with ZeroTier's root-owned state, not packaged dashboard/source archives.

## WireGuard

Policy follows `~/git/wireguard/README.md`: destination routing for OpenAI domains, ordinary traffic remains on LAN. Pi uses a separately generated key and separately registered IVPN device/session; does not reuse Mac's private key/address. Registration used official IVPN session API without forcing logout of another device.

Current interface `ivpn-openai`, address `172.25.238.108/32`, MTU 1380, persistent keepalive 25 seconds. Successful peer:

```ini
Endpoint = 185.135.77.81:443
PublicKey = YuhEd9+a90/+uucZC+qzsyMHkfe/GiwG1dq7g2HegXQ=
```

Japan jp2 endpoint worked. Taipei original and Singapore candidates did not produce a handshake under tested conditions. This does not establish those servers are defective.

Root configuration `/etc/wireguard/ivpn-openai.conf` mode 0600. Pi key `/home/gareth/.config/pi-network/wireguard.key` mode 0600. Public configuration beside it records address, peer, selected routes and domain set. Account/session secrets were not committed or bundled; account registration response remains privately stored on local Mac at `~/.config/pi-network-setup/ivpn-session.json` mode 0600.

Selected domains: chatgpt.com, auth.openai.com, api.openai.com, auth.api.openai.org, ab.chatgpt.com, persistent.oaistatic.com, developers.openai.com, learn.chatgpt.com. Current validated IPv4 `/32` addresses only; IP routing also affects other services sharing these exact addresses. No full-tunnel `0.0.0.0/0` route. Pi currently has no IPv6 internet default route; IPv6 VPN routing is not implemented/claimed. If adding IPv6 internet, provide provider-supported IPv6 tunnel address/routes and validate `/128` destinations before relying on this policy for IPv6.

Initial Pi DNS returned different, unreachable OpenAI addresses. Bootstrap used working local DNS; subsequent refresh uses HTTPS DNS through VPN. Extra selected route `1.0.0.1/32` carries resolver only, with `1.0.0.1 cloudflare-dns.com # PI CODEX DOH` host mapping. `1.1.1.1` remains ordinary route. System DNS settings untouched; selected service names have explicit IPv4 entries inside managed `/etc/hosts` block. Original hosts backup `/etc/hosts.before-pi-codex`.

`/usr/local/lib/pi-codex/refresh-routes.py` resolves domains through HTTPS DNS, validates IPv4 `/32` addresses, updates routes before host mappings, persists peer AllowedIPs and preserves old routes. Missing any required resolution retains existing routes/mappings and fails visibly. Current old exact addresses retained; no broad address ranges introduced. `pi-codex-routes.timer` runs two minutes after boot and every 15 minutes. Root network exporter runs every 15 seconds and saves only handshake timestamp and ZeroTier membership/IP status.

```sh
sudo systemctl status wg-quick@ivpn-openai --no-pager
sudo wg show ivpn-openai latest-handshakes
ip route get "$(getent ahostsv4 api.openai.com | head -n1 | cut -d ' ' -f1)"
ip route get 1.1.1.1
curl --max-time 10 https://api.openai.com/cdn-cgi/trace
sudo systemctl start pi-codex-routes.service
journalctl -u pi-codex-routes -n 10 --no-pager
```

For a new Pi, install wireguard-tools, generate a new key with `wg genkey`, register a new IVPN device/session using authorized account access, and assign its returned tunnel address. Do not clone existing private key/address. Supply public configuration and key before running `configure-wireguard.py`; it is specific to user gareth. `probe-vpn.py` was an installation diagnostic, not a periodic job.

## Codex

Official release `rust-v0.161.0` arm64 Linux musl package, downloaded size 152,344,323 bytes. SHA256 verified:

```text
3c02e2ae34be0d06e62557e98fc5c0a783bec5a2fed406fe00e565803bf84ee8
```

Source: https://github.com/openai/codex/releases/download/rust-v0.161.0/codex-package-aarch64-unknown-linux-musl.tar.gz

Installed full package under `/home/gareth/.local/share/codex/0.161.0`; launcher symlink `~/.local/bin/codex`. No Node dependency. Existing authorized ChatGPT login migrated to Pi's `~/.codex/auth.json`, mode 0600. New-device setup must authenticate its own account with `codex login` or an authorized credential migration; credentials not part of source archive. User config requests approval policy never, danger-full-access and medium reasoning. No project/GSD skills installed for this task.

```sh
~/.local/bin/codex --version
~/.local/bin/codex login status
~/.local/bin/codex app-server daemon version
~/.local/bin/codex agents
~/.local/bin/codex --remote unix:// --cd ~/git
```

Managed daemon bootstrap supplies versioned daemon package; boot service `codex-daemon.service` starts it as gareth, after WireGuard. Socket `~/.codex/app-server-control/app-server-control.sock`. It uses WebSocket JSON-RPC over Unix socket, not raw NDJSON. Protocol inspected from installed 0.161.0 JSON schema and exact tag's `codex-rs/app-server-client/src/remote.rs`; handshake URL `ws://localhost/rpc`. No public TCP listener or remote-control account link needed for this dashboard.

## Dashboard and recovery

Independent source local `../eink-codex`, Pi `/home/gareth/git/hardware/eink-codex`. Its README contains pin table, inspected 3 Ω configuration, dependencies, commands and count semantics. Included app and driver wheels, source archive and checksums permit reinstall. Root status/helper installation script `scripts/pi-codex-setup/install-services.sh` uses Pi-specific paths and already-provisioned public configuration. Review paths for a differently named account.

`eink-codex.service` owns panel; previous `eink-bitcoin.service` disabled gracefully, source/unit retained. Persistent viewer `pi-codex-setup:codex-dashboard`. Managed agents continue through SSH disconnects. Desktop resolution, fan wiring, and panel voltages/waveforms unchanged.

To remove this setup, stop dashboard before its daemon, then route/network services:

```sh
sudo systemctl disable --now eink-codex codex-daemon pi-codex-routes.timer pi-codex-network-status.timer
sudo systemctl stop pi-codex-routes.service pi-codex-network-status.service
sudo systemctl disable --now wg-quick@ivpn-openai
sudo zerotier-cli leave 8d1c312afae039bc
```

Remove only `# BEGIN PI CODEX OPENAI` through `# END PI CODEX OPENAI` managed block and `# PI CODEX DOH` line from hosts. Do not blindly overwrite hosts backup if unrelated edits occurred later. Restore Bitcoin with `sudo systemctl enable --now eink-bitcoin` only after Codex dashboard stops. Removing an IVPN account device is a separate account action; do not revoke other sessions.

## Force ZeroTier transport over plain Wi-Fi

Added after authorization at user's request. ZeroTier transport must use wlan0, never ivpn-openai; other applications keep selected WireGuard routes.

Observed before change: ZeroTier had UDP sockets bound to both 192.168.50.191 (Wi-Fi) and 172.25.238.108 (WireGuard). Existing peer destinations used Wi-Fi but that alone did not guarantee future paths.

Implemented three layers:

- `local.conf` interfacePrefixBlacklist excludes ivpn-openai, wg, tun, tap, utun and zt prefixes. Existing unrelated settings preserved. Daemon now binds its UDP sockets only to Wi-Fi address.
- nftables `inet zt_wifi_only` identifies **zerotier-one.service cgroup sockets**, including all UDP ports/TCP sockets, and sets packet mark 0x5a54 in output route hook. IPv4/IPv6 priority-1050 rules send marked packets to dedicated table 42000 containing only wlan0 routes.
- Postrouting guard drops marked service packets routed to interfaces other than wlan0/lo. Dedicated table has unreachable default when Wi-Fi lacks a route; no fallback to main/WireGuard. IPv6 Wi-Fi routes can be copied when available; absent current IPv6 internet route is terminal unreachable. Overlay IPv6 still transports inside normal IPv4 ZeroTier packets.

No full firewall flush or changes to unrelated rules. Wi-Fi DHCP/link changes update table via root NetworkManager dispatcher. ZeroTier ExecStartPre rebuilds nft rule against current cgroup ID on every daemon start, avoiding stale cgroup references across restart/boot. Wi-Fi outage means ZeroTier loses external connectivity instead of using VPN. Current IPv4 Wi-Fi gateway/address discovered dynamically, not hardcoded in installer.

Source and installer `scripts/pi-codex-setup/zerotier-wifi.py`, `install-zerotier-wifi.sh`; three automated route/ruleset tests passed. Installed root helper `/usr/local/lib/pi-codex/zerotier-wifi.py`, service drop-in `/etc/systemd/system/zerotier-one.service.d/wifi-only.conf`, dispatcher `/etc/NetworkManager/dispatcher.d/90-zerotier-wifi`. Requires nftables/iproute2/cgroupv2 on this Pi. tcpdump 4.99.5 installed for bounded packet validation, not a background capture.

Executed verification: daemon restarted; membership remained OK; 3/3 peer pings passed. Real ZeroTier UDP captures showed wlan0 output. cgroup mark counter increased, prohibited-egress counter remained zero. Controlled 13-byte UDP route probe inside ZeroTier cgroup, bound to Wi-Fi source, reached an address otherwise routed through WireGuard via wlan0. Initial probe found an output-hook guard error: output interface metadata still represented original route after rerouting. Guard moved to postrouting so it checks final egress; repeat probe verified Wi-Fi transmission. Normal OpenAI HTTPS still used VPN exit 185.135.77.63. Dispatcher route-refresh path tested; actual DHCP renewal, Wi-Fi outage and reboot not induced.

```sh
sudo nft list table inet zt_wifi_only
ip -4 rule show
ip -6 rule show
ip -4 route show table 42000
ip -6 route show table 42000
# Same destination, different routing policies:
ip route get 162.159.140.245 mark 0x5a54
ip route get 162.159.140.245
sudo ss -uapn | sed -n '/zerotier/p'
sudo /usr/local/lib/pi-codex/zerotier-wifi.py --routes-only
```

Rollback: stop ZeroTier first. Remove only its Wi-Fi drop-in/dispatcher and nft table; delete exact priority-1050 mark rules and flush table 42000 for both address families. Restore `local.conf.before-wifi-only` if present and no later changes occurred; otherwise remove only the added blacklist prefixes, preserving later configuration. Reload systemd and restart ZeroTier. Do not flush the global ruleset or modify OpenAI VPN routes.

Primary references: [ZeroTier client configuration](https://docs.zerotier.com/config/), [nftables socket cgroupv2 and route hooks](https://www.netfilter.org/projects/nftables/manpage.html).
