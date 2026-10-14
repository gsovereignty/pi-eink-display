"""Write-only mode-0 SPI with two manually owned, active-low selects."""
import errno
import glob
import hashlib
import os
import re
import time
from pathlib import Path

from .config import PINS


class DeadlineExceeded(TimeoutError):
    pass


class Clock:
    def now(self):
        return time.monotonic()

    def sleep(self, seconds):
        time.sleep(seconds)


class FakeClock(Clock):
    def __init__(self):
        self.value = 0.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Budget:
    def __init__(self, seconds, clock=None):
        self.clock = clock or Clock()
        self.end = self.clock.now() + seconds

    def check(self):
        if self.clock.now() >= self.end:
            raise DeadlineExceeded("Overall test deadline exceeded")

    def sleep(self, seconds):
        self.check()
        if self.clock.now() + seconds >= self.end:
            raise DeadlineExceeded("Insufficient overall deadline for requested delay")
        self.clock.sleep(seconds)
        self.check()


def chip_info(lgpio, handle):
    info = lgpio.gpio_get_chip_info(handle)
    if len(info) == 4:
        return tuple(info[1:])  # installed Pi binding: [chip, lines, name, label]
    if len(info) == 3:
        return tuple(info)
    raise RuntimeError(f"Unsupported lgpio chip-info format: {info}")


def line_info(lgpio, handle, line):
    info = lgpio.gpio_get_line_info(handle, line)
    if len(info) == 5:
        return tuple(info[1:])  # installed Pi binding: [chip, line, flags, name, user]
    if len(info) == 4:
        return tuple(info)
    raise RuntimeError(f"Unsupported lgpio line-info format: {info}")


def discover_chip(lgpio):
    """Match RP1 label AND header line names; deduplicate compatibility symlinks."""
    candidates = []
    paths = sorted({os.path.realpath(p) for p in glob.glob("/dev/gpiochip*")})
    for path in paths:
        number = int(Path(path).name.removeprefix("gpiochip"))
        handle = lgpio.gpiochip_open(number)
        try:
            lines, name, label = chip_info(lgpio, handle)
            names = {n: line_info(lgpio, handle, n)[2]
                     for n in PINS.values() if n < lines}
            if "rp1" in (name + " " + label).lower() and all(
                    names.get(n) == f"GPIO{n}" for n in PINS.values()):
                candidates.append((number, path, label))
        finally:
            lgpio.gpiochip_close(handle)
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one RP1 header GPIO chip, found {candidates}")
    return candidates[0]


class Transport:
    def __init__(self, gpio, spi, config, budget, emit=lambda *a, **k: None):
        self.gpio, self.spi, self.config, self.budget = gpio, spi, config, budget
        self.emit = emit
        self.closed = False

    def write(self, targets, data_mode, payload):
        self.budget.check()
        if self.closed or not targets or set(targets) - {"cs1", "cs2"}:
            raise RuntimeError("Invalid transport state or selects")
        self.deselect()
        self.gpio.write(PINS["dc"], int(data_mode))
        # 10 us guard exceeds SSD1608 D/C and CS setup/hold minimums.
        self.budget.sleep(0.00001)
        try:
            for target in targets:
                self.gpio.write(PINS[target], 0)
            self.budget.sleep(0.00001)
            for start in range(0, len(payload), 1024):
                self.budget.check()
                self.spi.writebytes2(payload[start:start + 1024])
            self.budget.sleep(0.00001)
            self.emit("transfer", targets=list(targets), dc=int(data_mode),
                      length=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                      hex=payload.hex() if len(payload) <= 40 else None)
        finally:
            self.deselect()

    def reset(self):
        self.deselect()
        self.gpio.write(PINS["reset"], 1)
        self.budget.sleep(self.config.reset_seconds)
        self.gpio.write(PINS["reset"], 0)
        self.budget.sleep(self.config.reset_seconds)
        self.gpio.write(PINS["reset"], 1)
        self.budget.sleep(self.config.reset_seconds)
        self.emit("reset", pulse_seconds=self.config.reset_seconds)

    def busy(self):
        self.budget.check()
        return self.gpio.read(PINS["busy"])

    def deselect(self):
        # Cleanup must remain available after the deadline expires.
        errors = []
        for pin in (PINS["cs1"], PINS["cs2"]):
            try:
                self.gpio.write(pin, 1)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("CS deassertion failed: " + "; ".join(errors))

    def close(self):
        if self.closed:
            return
        errors = []
        for operation in (self.deselect, self.spi.close, self.gpio.close):
            try:
                operation()
            except BaseException as exc:
                errors.append(str(exc))
        self.closed = True
        self.emit("transport_closed", errors=errors, physical_power_removed=False)
        if errors:
            raise RuntimeError("Cleanup errors: " + "; ".join(errors))


class MockGPIO:
    def __init__(self, clock, busy_values=None):
        self.clock = clock
        self.claims = {PINS[k]: "output" for k in ("cs1", "cs2", "dc", "reset")}
        self.claims[PINS["busy"]] = "input"
        self.values = {PINS["cs1"]: 1, PINS["cs2"]: 1, PINS["reset"]: 1, PINS["dc"]: 0}
        self.events = []
        self.busy_values = iter(busy_values) if busy_values is not None else None
        self.last_busy = 0
        self.busy_until = 0.0
        self.closed = False

    def write(self, pin, value):
        if self.claims.get(pin) != "output":
            raise RuntimeError("Attempted to drive an input/unclaimed line")
        self.values[pin] = value
        self.events.append((self.clock.now(), pin, value))

    def read(self, pin):
        if pin != PINS["busy"]:
            raise RuntimeError("Only BUSY is an input")
        if self.busy_values is not None:
            self.last_busy = next(self.busy_values, self.last_busy)
            return self.last_busy
        return int(self.clock.now() < self.busy_until)

    def close(self):
        self.closed = True


class MockSPI:
    def __init__(self, gpio):
        self.gpio = gpio
        self.writes = []
        self.closed = False
        self.fail_at = None

    def writebytes2(self, data):
        if self.fail_at == len(self.writes):
            raise OSError("Injected SPI failure")
        selected = tuple(k for k in ("cs1", "cs2") if self.gpio.values[PINS[k]] == 0)
        dc = self.gpio.values[PINS["dc"]]
        self.writes.append((selected, dc, bytes(data)))
        if dc == 0 and bytes(data) in (b"\x12", b"\x20"):
            self.gpio.busy_until = self.gpio.clock.now() + 0.05

    def close(self):
        self.closed = True


def mock_transport(config, budget, emit=lambda *a, **k: None, busy_values=None):
    gpio = MockGPIO(budget.clock, busy_values)
    return Transport(gpio, MockSPI(gpio), config, budget, emit)


class LGPIO:
    def __init__(self, module, handle):
        self.module, self.handle = module, handle
        self.claimed = []

    def claim(self):
        # CS high first. BUSY is NEVER claimed as output, including cleanup.
        for key, value in (("cs1", 1), ("cs2", 1), ("dc", 0), ("reset", 1)):
            pin = PINS[key]
            self.module.gpio_claim_output(self.handle, pin, value)
            self.claimed.append(pin)
        self.module.gpio_claim_input(self.handle, PINS["busy"])
        self.claimed.append(PINS["busy"])

    def write(self, pin, value):
        if pin == PINS["busy"]:
            raise RuntimeError("BUSY must remain input")
        self.module.gpio_write(self.handle, pin, value)

    def read(self, pin):
        return self.module.gpio_read(self.handle, pin)

    def close(self):
        errors = []
        try:
            for pin in reversed(self.claimed):
                try:
                    self.module.gpio_free(self.handle, pin)
                except Exception as exc:
                    errors.append(str(exc))
        finally:
            self.module.gpiochip_close(self.handle)
        if errors:
            raise RuntimeError("GPIO release failures: " + "; ".join(errors))


def verify_unrouted_kernel_cs(spi_path):
    """Fail closed on kernels rejecting SPI_NO_CS; inspect live overlay properties."""
    device = re.fullmatch(r"/dev/spidev(\d+)\.(\d+)", os.path.realpath(spi_path))
    if device is None:
        raise RuntimeError("Cannot verify kernel CS routing")
    node = Path(f"/sys/class/spi_master/spi{device[1]}/device/of_node")
    if (node / "cs-gpios").read_bytes() != b"":
        raise RuntimeError("Kernel CS GPIO routing is not empty")
    refs = (node / "pinctrl-0").read_bytes()
    handles = {refs[i:i+4] for i in range(0,len(refs),4)}
    found = set()
    pins = set()
    for phandle in Path("/sys/firmware/devicetree/base").rglob("phandle"):
        value = phandle.read_bytes()
        if value in handles:
            raw = (phandle.parent / "brcm,pins").read_bytes()
            if len(raw) % 4:
                raise RuntimeError("Malformed pinctrl property")
            pins.update(int.from_bytes(raw[i:i+4], "big") for i in range(0,len(raw),4))
            found.add(value)
    if found != handles or not handles or pins != {10,11}:
        raise RuntimeError(f"Kernel SPI pins are not MOSI/clock only: {pins}")
    return {"cs_gpios_empty": True, "kernel_spi_pins": sorted(pins)}


def live_transport(config, budget, emit=lambda *a, **k: None):
    import lgpio
    import spidev
    number, path, label = discover_chip(lgpio)
    handle = lgpio.gpiochip_open(number)
    gpio = LGPIO(lgpio, handle)
    spi = spidev.SpiDev()
    try:
        for key in ("cs1", "cs2", "dc", "reset", "busy"):
            info = line_info(lgpio, handle, PINS[key])
            if info[1] & 1 or info[3]:
                raise RuntimeError(f"GPIO{PINS[key]} owned: {info}; use spi0-0cs,no_miso")
        gpio.claim()  # Actual exclusive claims, not merely a no_cs assumption.
        if hasattr(spi, "open_path"):
            spi.open_path(config.spi_path)
        else:
            device = re.fullmatch(r"/dev/spidev(\d+)\.(\d+)", os.path.realpath(config.spi_path))
            if device is None:
                raise RuntimeError("SPI path must resolve to /dev/spidevBUS.DEVICE")
            spi.open(int(device[1]), int(device[2]))
        try:
            spi.no_cs = True
        except OSError as exc:
            if exc.errno != errno.EINVAL:
                raise
            # RP1 dw-apb-ssi may reject SPI_NO_CS. GPIO ownership was already
            # claimed exclusively; live DT must also prove native CS unmapped.
            evidence = verify_unrouted_kernel_cs(config.spi_path)
            emit("spi_no_cs_unsupported", **evidence, manual_cs_exclusively_claimed=True)
        spi.mode = config.spi_mode
        spi.max_speed_hz = config.speed_hz
        spi.bits_per_word = 8
        spi.lsbfirst = False
        emit("transport_open", chip=path, label=label, config=config.record())
        return Transport(gpio, spi, config, budget, emit)
    except BaseException:
        try:
            for pin in (PINS["cs1"], PINS["cs2"]):
                if pin in gpio.claimed:
                    try:
                        gpio.write(pin, 1)
                    except Exception as exc:
                        emit("setup_cleanup_error", pin=pin, error=str(exc))
        finally:
            try:
                spi.close()
            finally:
                gpio.close()
        raise
