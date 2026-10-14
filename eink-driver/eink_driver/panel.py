"""Full/partial-refresh port of xljxlj's GxEPD2_2IC_420_A03, library 1.4.8.

Upstream: eink_driver/upstream/GxEPD2_2IC_420_A03.cpp (GPL-3.0).
Exact upstream partial waveform only; no OTP, voltage sweep or automatic retry.
"""
from .images import split_rows

BOTH = ("cs1", "cs2")
LUT_FULL = bytes.fromhex(
    "50 aa 55 aa 11 00 00 00 00 00 00 00 00 00 00 "
    "00 00 00 00 00 ff ff 1f 00 00 00 00 00 00 00")
LUT_PART = bytes.fromhex("10 18 18 08 18 18 08 00 00 00 00 00 00 00 00 00 00 00 00 00 13 14 44 12 00 00 00 00 00 00")


def changed_bands(previous, current):
    """Changed full-width row bands; bridge up to three blank glyph rows."""
    if len(previous)!=15000 or len(current)!=15000:
        raise ValueError("Expected two 15000-byte frames")
    rows=[y for y in range(300) if previous[y*50:(y+1)*50]!=current[y*50:(y+1)*50]]
    bands=[]
    for y in rows:
        if bands and y-bands[-1][1]<=4:bands[-1]=(bands[-1][0],y)
        else:bands.append((y,y))
    return bands


INIT = ((0x01, bytes.fromhex("2b 01 00")),
        (0x0c, bytes.fromhex("d7 d6 9d")),
        (0x2c, b"\xa8"), (0x3a, b"\x1a"), (0x3b, b"\x08"))
RAM_AREA = ((0x11, b"\x03"), (0x44, b"\x00\x18"),
            (0x45, b"\x00\x00\x2b\x01"), (0x4e, b"\x00"), (0x4f, b"\x00\x00"))
# Explicit whitelist excludes OTP commands, VCOM sensing and unsupported refresh modes.
ALLOWED = {0x01,0x0c,0x2c,0x3a,0x3b,0x11,0x44,0x45,0x4e,0x4f,0x32,0x22,0x20,0xff,0x24,0x10}


class BusyTimeout(TimeoutError):
    pass


class BusyNotObserved(RuntimeError):
    pass


class Panel:
    def __init__(self, transport):
        self.t = transport
        self.state = "new"
        self.powered = False
        self.last_refresh = None
        self.refresh_count = 0
        self.busy_records = []
        self.partial_mode = False

    def _check(self):
        self.t.budget.check()
        if self.state in ("failed", "closed"):
            raise RuntimeError("Panel failed/closed: power-cycle and investigate; no retries")

    def wait_ready(self, label, require_busy=False):
        start = self.t.budget.clock.now()
        end = start + self.t.config.busy_timeout
        transitions = []
        last = None
        seen = False
        # Poll immediately, then every millisecond. A short missed pulse is INCONCLUSIVE.
        try:
            while True:
                level = self.t.busy()
                elapsed = self.t.budget.clock.now() - start
                if level != last:
                    transitions.append({"seconds": round(elapsed, 6), "level": level})
                    last = level
                seen |= level == self.t.config.busy_active
                if level != self.t.config.busy_active and (seen or not require_busy):
                    break
                if self.t.budget.clock.now() >= end:
                    if not seen and require_busy:
                        raise BusyNotObserved(f"{label}: BUSY never asserted; write-only panel presence unproved")
                    raise BusyTimeout(f"{label}: BUSY active beyond {self.t.config.busy_timeout}s")
                self.t.budget.sleep(0.001)
        except BaseException:
            self.state = "failed"
            raise
        finally:
            record = {"label": label, "duration_seconds": self.t.budget.clock.now()-start,
                      "active_observed": seen, "transitions": transitions}
            self.busy_records.append(record)
            self.t.emit("busy_wait", **record)
        return record

    def command(self, command, data=b"", targets=BOTH):
        self._check()
        if command not in ALLOWED:
            raise ValueError("Command not in fixed full-refresh reference whitelist")
        try:
            self.wait_ready(f"before_{command:02x}")
            self.t.write(targets, False, bytes([command]))
            if data:
                self.t.write(targets, True, data)
        except BaseException:
            self.state = "failed"
            raise

    def init(self):
        self._check()
        if self.state not in ("new", "sleeping"):
            raise RuntimeError("Initialization allowed only on new/sleeping panel")
        try:
            self.t.reset()
            self.wait_ready("after_reset")
            for command, data in INIT + RAM_AREA:
                self.command(command, data)
            self.command(0x32, LUT_FULL)
            self.partial_mode = False
            self.state = "ready"  # Digital configuration only; booster still off.
        except BaseException:
            self.state = "failed"
            raise

    def power_on(self):
        if self.state != "ready":
            raise RuntimeError("Power-on requires initialized ready panel")
        self.command(0x22, b"\xc0")
        self.command(0x20)
        self.powered = True  # Unknown if the wait fails; never send power-off into BUSY.
        self.wait_ready("power_on", require_busy=True)

    def write_frame(self, frame):
        self._check()
        if self.state != "ready":
            raise RuntimeError("Framebuffer requires ready panel")
        planes = split_rows(frame)
        targets = ("cs2", "cs1") if self.t.config.swap_cs else ("cs1", "cs2")
        for target, plane in zip(targets, planes):
            for command, data in RAM_AREA:
                self.command(command, data, (target,))
            self.command(0x24, plane, (target,))

    def refresh(self):
        self._check()
        if self.state != "ready":
            raise RuntimeError("Full refresh requires ready panel")
        if self.last_refresh is not None:
            delay = self.t.config.spacing - (self.t.budget.clock.now()-self.last_refresh)
            if delay > 0:
                self.t.emit("refresh_spacing", seconds=delay)
                self.t.budget.sleep(delay)
        if self.partial_mode:
            self.command(0x32, LUT_FULL)
            self.partial_mode = False
        if not self.powered:
            self.power_on()
        self.command(0x22, b"\xc4")
        self.command(0x20)
        self.refresh_count += 1
        record = self.wait_ready("full_refresh", require_busy=True)
        self.command(0xff)
        self.last_refresh = self.t.budget.clock.now()
        return record

    def update_changed(self, previous, frame):
        """Upstream _Init_Part/_Update_Part, independent 200-pixel RAM planes.

        Caller supplies the last successfully displayed full baseline. No reset,
        clearScreen, full refresh or retry occurs here.
        """
        self._check()
        if self.state != "ready" or not self.refresh_count:
            raise RuntimeError("Partial update requires successful full baseline")
        bands=changed_bands(previous,frame)
        if not bands:return {"duration_seconds":0,"active_observed":False,"bands":[]}
        for command,data in INIT+RAM_AREA:self.command(command,data)
        self.command(0x32,LUT_PART)
        self.partial_mode=True
        # Keep complete current-image RAM populated on both controllers.
        # A full RAM upload is not a full waveform refresh.
        self.write_frame(frame)
        # RAM write windows are not the display scan geometry. Restore both
        # controllers to their complete 200x300 window before the one activation,
        # matching the upstream refresh(true) sequence.
        for command,data in RAM_AREA:self.command(command,data)
        if not self.powered:self.power_on()
        self.command(0x22,b"\x04")
        self.command(0x20)
        self.refresh_count+=1
        record=self.wait_ready("partial_refresh",require_busy=True)
        self.command(0xff)
        self.last_refresh=self.t.budget.clock.now()
        return {"duration_seconds":record['duration_seconds'],
                "active_observed":record['active_observed'],"bands":bands}

    def power_off(self):
        self._check()
        if self.state != "ready":
            raise RuntimeError("Normal power-off requires ready panel")
        if self.powered:
            self.command(0x22, b"\xc3")
            self.command(0x20)
            self.wait_ready("power_off", require_busy=True)
            self.powered = False

    def sleep(self):
        self.power_off()
        self.command(0x10, b"\x01")
        self.state = "sleeping"

    def abort(self):
        # No controller command in unknown/stalled state. GPIO release is NOT power removal.
        self.state = "failed"
        self.t.deselect()
        self.t.emit("aborted", remove_adapter_power_manually=True)

    def close(self):
        try:
            if self.state == "ready":
                self.sleep()
        finally:
            self.t.close()
            self.state = "closed"
