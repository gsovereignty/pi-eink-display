# Driver and electrical evidence

Retrieved 2026-10-07, Asia/Shanghai (+08:00). Byte hashes in
[manifest.json](manifest.json); originals retained locally.

| Source | Version / finding |
|---|---|
| [Working exact-panel example](https://lingshunlab.com/book/esp32/teardown-and-activation-esp32-driving-used-hanshow-4-2-inch-e-ink-display-part-2) | Published 2024-07-29. Names `GxEPD2_2IC_420_A03`; demonstrates a new complete image using two independent selects. Board needed FPC pin 1 access. This is evidence of that setup, not proof of this adapter. |
| [Original xljxlj project](https://oshwhub.com/xljxlj/4-2-cun-mo-shui-ping-_-qu-dong-ban) | Updated 2023-10-08. Corrected URL found through search; article's shorter URL returns 404. GPL-3.0. Author warns that 470 mΩ vs 2.2 Ω depends on panel. |
| [Original archive](https://image.lceda.cn/attachments/2023/3/nWegHjTzPGBFA43Agksn1ojhHHlMQUbMzLKeCfPY.zip) | 11,291,039 bytes; advertised MD5 `e353a842397b356a57464ce8f3169656` verified, all ZIP CRCs verified. Nested library version 1.4.8. Exact panel files credit xljxlj; base library Jean-Marc Zingg. This is a modified library, not stock GxEPD2 1.4.8. |
| [SSD1608 manufacturer datasheet](https://cdn-learn.adafruit.com/assets/assets/000/099/574/original/SSD1608.pdf) | Solomon Systech Rev 1.2, February 2015. p8 active-high BUSY; slave BUSY left open in cascade. p51 mode-0-like timing, MSB first, 250 ns minimum clock cycle. p53 reference R1=2.2 Ω at RESE, MOSFET/inductor circuit. Retrieved PDF hash differs from archive's SSD1608 PDF; port uses actual exact-panel library, not defaults from either PDF. |
| [HINK panel datasheet](https://www.texim-europe.com/getfile.aspx?id=108187) | Direct current download unavailable (certificate issue/404). Original PDF recovered from xljxlj archive: HINK-E042A03, A/0, 2015-01-08, 33 specification pages plus distributor page. Internal headers sometimes say E042A01; document inconsistencies retained as uncertainties. p7: FPC 12=CS# master, FPC 1=CS1# slave. p24: 7500 bytes per half, VCOM and LUT batch-specific. |
| [Raspberry Pi hardware docs](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html) and [overlay README](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README) | Live Pi kernel 6.18.34+rpt-rpi-2712; local `/boot/firmware/overlays/README` confirms `spi0-0cs,no_miso`. Configuration must actually free GPIO7/8; `spidev.no_cs` alone cannot release kernel claims. |
| [GPIO Zero pin factories](https://gpiozero.readthedocs.io/en/stable/api_pins.html) | 2.0.1.post3 docs reviewed. Harness uses direct installed lgpio 0.2.2 rather than gpiozero, with RP1 label and header line-name discovery. Live binding returns extra chip ID fields; adapter supports observed format and known shorter format. |
| [Waveshare driver HAT guidance](https://www.waveshare.com/wiki/E-Paper_Driver_HAT) | General guidance reviewed; [Waveshare's explicit 180-second recommendation](https://www.waveshare.com/wiki/13.3inch_e-Paper_HAT) adopted conservatively. Not a HINK-specific refresh-spacing specification and not a substitute panel driver. HINK PDF does not state a minimum inter-refresh interval; working Arduino example uses short demonstration delays, not lifetime guidance. |

## Fixed port and deliberate changes

`GxEPD2_2IC_420_A03::_InitDisplay`: broadcast `01 2b 01 00`,
`0c d7 d6 9d`, `2c a8`, `3a 1a`, `3b 08`. Full RAM entry mode `11 03`,
X range `44 00 18`, Y range `45 00 00 2b 01`, counters X=0, Y=0.
Broadcast full LUT command `32` followed by exactly the upstream 30 bytes.
Booster on: `22 c0; 20`. Full update: `22 c4; 20`, BUSY wait, `ff`.
Normal booster off: `22 c3; 20`, BUSY wait. Sleep: `10 01`; wake by reset.

The circulating sample uses VCOM `b9`, a different LUT, entry mode `01` and
update `c7`; those values are **not** mixed into this port. No OTP command,
voltage sweep, booster sweep, partial-refresh LUT or fast mode is exposed by CLI.

Reset matches base class: HIGH 10 ms, LOW 10 ms, HIGH 10 ms. SPI mode 0,
MSB first, 100 kHz (reference uses 4 MHz); 10 µs D/C and CS guards. Timing
guards exceed manufacturer minimums; actual edges require analyzer confirmation.

Booster-on is deferred until RAM is loaded. Identical full-register sequence
otherwise: compiling the original C++ against a recording shim verifies init,
power-on, refresh, power-off and sleep. The harness does not call upstream
`clearScreen`/`writeScreenBuffer`, which can introduce automatic extra refreshes
and partial-mode initialization. Each requested pattern gets exactly one full
refresh. Booster is off during waits and observations.

For full 400x300 input, upstream `writeImage` indexes `i*50+j`; j=0..24 goes
to m=1 (`_cs`), j=25..49 to m=2 (`_cs1`). Python collects those bytes row-wise
into two 7500-byte streams. Actual original C++ execution validates every byte
using nonuniform rows; artifacts in `software/reference-*`. Logical rotation is
applied before packing; bit 7 is leftmost pixel, 1=white, 0=black. Both controllers
use identical increasing-X/Y addressing; no guessed mirroring.

## Uncertainties requiring observations

* **BUSY:** panel p8 prose says active-low, but panel p24 flow says BUSY high
  during update; SSD1608 p8 and actual library constructor say active-high.
  Harness pins active-high. Unexpected idle high triggers a bounded failure,
  not a polarity flip or retry. Measure BUSY versus reset/refresh before changing
  evidence-backed settings. One master BUSY signal cannot validate slave image.
* **VCOM/LUT:** `a8` and 30-byte full LUT are established for the working class,
  not measured/calibrated for this SYX 1734 / 2016-04-13 batch. Manufacturer says
  values vary by batch. Do not experiment with voltages to cure blank output.
* **Adapter routing:** adapter CS1/CS2 names may not match panel CS#/CS1#.
  Harness defaults reference m=1/left to BCM8 (adapter CS1), m=2/right to BCM7
  (adapter CS2). Powered-off continuity or labeled full-screen observations must
  confirm. `--swap-cs` records a controlled mapping correction and requires a new
  smoke; it is never tried automatically.
* **RESE:** 3 Ω is a monitored experimental starting configuration, not 2.2 Ω
  equivalence. 0.47 Ω is ~4.7 times lower than reference 2.2 Ω; actual peak
  current depends on circuit and controller regulation. Do not infer current
  from resistor ratio alone. Missing adapter topology/inductor/MOSFET ratings
  and exact-panel validation block live 0.47 Ω execution. Both mock/dry suites
  and results recording support it.
* **Temperature/power:** HINK p17/18 specify VCI 2.4–3.7 V and 0–50°C operation.
  p18 update current max 12 mA concerns panel at stated test conditions, not
  total adapter supply or switching peaks. No adapter-specific current or
  component temperature limit is available. Temperature/supply/current remain
  unavailable until measured; stop on abnormalities rather than invent limits.

No failed update proves the adapter defective. Host transmission alone cannot
identify a panel with no MISO.

## User-requested partial extension, 2026-10-08

The monitor's changed-line extension supersedes the earlier full-only CLI scope
for this application. Exact pinned header has `hasPartialUpdate=true` and
`hasFastPartialUpdate=true`. `_Init_Part` reuses `_InitDisplay`, loads the existing
30-byte `LUTDefault_part`, then powers on; `_Update_Part` uses `22 04; 20`, BUSY, FF.
The Python port retains the existing deferred power-on after RAM upload, identical
LUT and update values. Regional RAM windows use the reference's 0x11/44/45/4E/4F.
No arbitrary Waveshare waveform, OTP or voltage tuning is used.


## Standalone extraction

2026-10-08 (+08:00): extracted existing validated Python driver without changing register values or transport. Partial updates now upload both complete controller RAM buffers, restore full scan windows, then trigger exactly one partial activation. Earlier regional-window wording above describes superseded implementation. No runtime import of original diagnostics workspace.
