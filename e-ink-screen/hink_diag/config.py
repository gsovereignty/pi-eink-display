from dataclasses import asdict, dataclass

PINS = {"mosi": 10, "clock": 11, "reset": 17, "dc": 25,
        "cs1": 8, "cs2": 7, "busy": 24}
HEADER = {"3v3": 1, "gnd": 14, "mosi": 19, "clock": 23,
          "reset": 11, "dc": 22, "cs1": 24, "cs2": 26, "busy": 18}


@dataclass(frozen=True)
class Config:
    spi_path: str = "/dev/spidev0.0"
    speed_hz: int = 100_000
    spi_mode: int = 0
    busy_active: int = 1
    busy_timeout: float = 20.0
    deadline: float = 1800.0
    spacing: float = 180.0
    rotation: int = 0
    swap_cs: bool = False
    resistor: str = "3"
    reset_seconds: float = 0.010

    def validate(self):
        if self.spi_mode != 0 or not 10_000 <= self.speed_hz <= 4_000_000:
            raise ValueError("Validated harness requires SPI mode 0, 10 kHz–4 MHz")
        if self.busy_active != 1:
            raise ValueError("Exact reference requires active-high BUSY")
        if not 0.1 <= self.busy_timeout <= 30 or not 1 <= self.deadline <= 3600:
            raise ValueError("Invalid bounded timeout")
        if not 0 <= self.spacing <= 3600:
            raise ValueError("Spacing must be 0–3600 seconds; default conservative spacing is 180")
        if self.rotation not in (0, 90, 180, 270) or self.resistor not in ("3", "0.47"):
            raise ValueError("Invalid rotation or recorded resistor position")
        if self.reset_seconds != 0.010:
            raise ValueError("Reset pulse pinned to reference 10 ms")

    def record(self):
        return {**asdict(self), "bcm_pins": PINS, "physical_header": HEADER,
                "bit_order": "MSB first", "polarity": "1 white, 0 black",
                "selector_verified_by_software": False}
