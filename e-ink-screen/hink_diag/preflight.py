"""Read-only inventory: never reset, transmit SPI, or enable booster."""
import glob
import importlib.metadata
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

from .config import PINS
from .transport import discover_chip, line_info


def command(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=8)
        return {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def inventory(config, sample_busy=False):
    result = {"python": sys.version, "executable": sys.executable,
              "platform": platform.platform(), "uname": list(platform.uname()),
              "model": None, "spi_devices": sorted(glob.glob("/dev/spidev*")),
              "gpio_devices": sorted(glob.glob("/dev/gpiochip*")),
              "libraries": {}, "checks": {}, "output_changes": False}
    model = Path("/proc/device-tree/model")
    if model.exists():
        result["model"] = model.read_bytes().rstrip(b"\0").decode()
    for name in ("lgpio", "spidev", "Pillow"):
        try:
            result["libraries"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result["libraries"][name] = None
    result["identity"] = command("id")
    result["pinctrl"] = command("pinctrl", "get", "7-11,17,24,25")
    for filename in ("/etc/os-release", "/boot/firmware/config.txt"):
        try:
            result[filename] = Path(filename).read_text()
        except OSError as exc:
            result[filename] = str(exc)
    result["checks"]["spi_device"] = "PASS" if os.access(config.spi_path, os.R_OK | os.W_OK) else "FAIL"
    result["checks"]["libraries"] = "PASS" if all(result["libraries"].values()) else "FAIL"
    try:
        import lgpio
        number, path, label = discover_chip(lgpio)
        handle = lgpio.gpiochip_open(number)
        try:
            result["gpio_chip"] = {"number": number, "path": path, "label": label}
            result["lines"] = {key: list(line_info(lgpio, handle, pin))
                               for key, pin in PINS.items()}
        finally:
            lgpio.gpiochip_close(handle)
        controls = ("cs1", "cs2", "reset", "dc", "busy")
        result["checks"]["control_lines_free"] = "PASS" if all(
            not (result["lines"][key][1] & 1) and not result["lines"][key][3]
            for key in controls) else "FAIL"
        if sample_busy:
            handle=lgpio.gpiochip_open(number)
            claimed=False
            try:
                busy=result["lines"]["busy"]
                if busy[1] & 1 or busy[3]:
                    raise RuntimeError("BUSY input already owned; not sampling")
                lgpio.gpio_claim_input(handle,PINS["busy"])
                claimed=True
                result["busy_samples"]=[]
                for _ in range(20):
                    result["busy_samples"].append(lgpio.gpio_read(handle,PINS["busy"]))
                    time.sleep(0.005)
                result["busy_sampling"]="input only, no output claims, no reset, no SPI"
            finally:
                try:
                    if claimed:lgpio.gpio_free(handle,PINS["busy"])
                finally:
                    lgpio.gpiochip_close(handle)
        result["gpioinfo"] = command("gpioinfo", "-c", path)
    except Exception as exc:
        result["gpio_error"] = str(exc)
        result["checks"]["gpio_access"] = "FAIL"
    result["checks"]["model"] = "PASS" if "Raspberry Pi 5" in (result["model"] or "") else "FAIL"
    # Successful writes cannot identify a write-only panel.
    result["panel_presence"] = "INCONCLUSIVE"
    return result
