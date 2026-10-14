# Full-refresh rate benchmark

This measures a short burst of distinct full-screen images with the fixed,
previously working HINK-E042A03-A1 full-refresh waveform. It does not measure
partial-refresh speed or establish a continuous-duty/lifetime rating.

## Evidence and timing

The archived exact-panel driver records a nominal full refresh of 1,600 ms.
Our previous hardware tests measured approximately 1.600 s of active BUSY.
This implies a **BUSY-only theoretical ceiling near 0.625 Hz**; actual distinct
frame throughput also includes RAM upload and command/software overhead.

The [SSD1608 manufacturer datasheet](https://cdn-learn.adafruit.com/assets/assets/000/099/574/original/SSD1608.pdf),
Table 12-4, and archived HINK specification give a minimum SPI cycle of 250 ns
and minimum high/low times of 100 ns. The exact working Arduino reference uses
mode 0 / MSB-first SPI at 4 MHz. Thus 4 MHz is the documented nominal SPI ceiling
used here; actual wire timing/load quality is not measured without an analyzer.
Raising SPI speed does not shorten the panel's fixed waveform itself.

Default diagnostic SPI speed remains 100 kHz. The CLI now permits 10 kHz–4 MHz.
No VCOM, LUT, booster or resistor changes accompany this test. Selector stays 3 Ω.

## Procedure

Power the Pi on with inspected wiring/ribbon unchanged and selector still at 3 Ω.
Run from `/home/gareth/git/hardware/e-ink-screen` in tmux. First validate software
and perform a fresh one-update smoke with the exact benchmark revision/settings:

```sh
python3 -m unittest discover -v
python3 scripts/reference_oracle.py
python3 -m hink_diag benchmark --mock --spacing 0 --speed-hz 4000000 --runs runs
python3 -m hink_diag preflight --hardware --sample-busy --runs runs
python3 -m hink_diag smoke --hardware --resistor 3 --spacing 0 --speed-hz 4000000 --inspection config/inspection.json --runs runs
```

Verify its new unique image across both halves, orientation/seam, and heat/supply
behaviour. Annotate the smoke with actual observations to obtain PASS. Then:

```sh
python3 -m hink_diag benchmark --hardware --resistor 3 --spacing 0 --speed-hz 4000000 --frames 3 --inspection config/inspection.json --smoke-run runs/SMOKE_RUN_ID --runs runs
```

Watch all three images: diagnostic `1/3`, inverted diagnostic `2/3`, normal
diagnostic `3/3`. Each carries the new benchmark run ID. Images are pre-generated
under the run's `patterns` directory before hardware initialization.

The short burst keeps the booster on between frames, as the exact reference
supports. Each next image is loaded only after the prior full update completes.
There is no intentional inter-frame spacing, retry or unbounded loop. Only two
or three frames are accepted. Each BUSY wait remains bounded; interruption and
the overall deadline stop the sequence. Final success performs normal power-off,
sleep and GPIO/SPI cleanup. Failed/unknown controller state receives no additional
controller commands; physical power removal remains manual.

Stop on abnormal heat, supply trouble, stall or visible defects. A failed fast-SPI
smoke stops progression; it does not trigger retries or speed fallback refreshes.

## Results

`result.json` contains per-frame `upload_seconds`, `refresh_seconds` (BUSY active
wait), `cycle_seconds` and completion times. `benchmark.csv` contains the timing
rows. The summary reports mean completion-to-completion interval and its reciprocal
in Hz; the first completion is excluded as the starting point, so initial
power-on does not distort steady burst intervals. It separately reports the
BUSY-only reciprocal, not as measured frame throughput. Final shutdown is outside
the frame interval. Mock timing is synthetic and does not count as hardware rate.

A hardware benchmark remains INCONCLUSIVE until all three distinct images and
heat/supply observations are verified. Annotate `steps.burst-1`, `steps.burst-2`
and `steps.burst-3` using the normal seven visual fields to record actual PASS/FAIL.
For two frames, only the two corresponding steps are required. Retention is not
required for this timing-specific benchmark; it was separately established in
the functional suite. Ordinary resistor-comparison results exclude benchmarks.

Absence of an analyzer, supply/current meter or adapter temperature probe must
remain explicit. A few successful updates establish observed short-burst rate,
not sustained maximum safe usage.

## Actual 3 Ω / 4 MHz run

Run `20261008-002145-132dd6`, 2026-10-08 00:21:45 UTC+08:00:
three full updates completed without software errors, followed by normal sleep.
Observed completion interval **1.6411 s**, throughput **0.6094 Hz**.
Uploads took approximately 0.037 s; BUSY durations 1.5992–1.6003 s.
First cycle included booster-on and took 1.7120 s; warm cycles 1.6385–1.6387 s.
Pi SoC temperature after burst 39.5 °C; firmware flags `throttled=0x0`.
Adapter electrical/thermal measurements unavailable. Visual confirmation pending.
[Raw result](../runs/20261008-002145-132dd6/result.json) ·
[Timing CSV](../runs/20261008-002145-132dd6/benchmark.csv).
