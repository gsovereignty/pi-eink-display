"""Read-only preflight, offline artifacts, and explicitly gated single refresh."""
import argparse
import json
import os
import signal
from datetime import datetime
from pathlib import Path

from .artifacts import TIMEZONE, code_version, save_json, timestamp
from .config import Config
from .images import PATTERNS, pack, pattern, split_rows
from .panel import Panel
from .preflight import inventory
from .transport import Budget, DeadlineExceeded, FakeClock, live_transport, mock_transport


def validate_inspection(path, config):
    if config.resistor != "3":
        raise ValueError("0.47 ohm execution blocked: missing adapter RESE/booster evidence")
    if not path:
        raise ValueError("Powered-off wiring/ribbon inspection required; supply --inspection JSON")
    record = json.loads(Path(path).read_text())
    required = ("all_power_disconnected_during_inspection", "ribbon_seated_contacts_checked",
                "wiring_matches_table", "fan_preserved", "no_visible_damage", "no_abnormal_heating")
    if not all(record.get(k) is True for k in required) or record.get("resistor") != config.resistor:
        raise ValueError("Incomplete inspection or selector mismatch")
    observer = record.get("observer", "")
    if not isinstance(observer, str) or not observer.strip() or "REPLACE" in observer:
        raise ValueError("Inspection requires named observer")
    try:
        confirmed = datetime.fromisoformat(record["confirmed_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Inspection requires ISO timestamp with UTC offset") from exc
    if confirmed.utcoffset() is None:
        raise ValueError("Inspection timestamp requires UTC offset")
    return record


def render_artifacts(directory, name, run_id, config):
    image = pattern(name, run_id, config.rotation)
    image.save(directory / "expected.png")
    frame = pack(image)
    left, right = split_rows(frame)
    (directory / "frame.bin").write_bytes(frame)
    (directory / "cs1.bin").write_bytes(right if config.swap_cs else left)
    (directory / "cs2.bin").write_bytes(left if config.swap_cs else right)
    return frame


def execute_refresh(config, frame, emit, hardware=False):
    budget = Budget(config.deadline, None if hardware else FakeClock())
    panel = None
    handlers = {}
    def interrupt(signum, _frame):
        if signum == signal.SIGALRM:
            raise DeadlineExceeded("Overall wall-clock deadline exceeded")
        raise KeyboardInterrupt(f"Interrupted by signal {signum}")
    try:
        if hardware:
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM):
                handlers[sig] = signal.signal(sig, interrupt)
            signal.setitimer(signal.ITIMER_REAL, config.deadline)
        transport = (live_transport if hardware else mock_transport)(config, budget, emit)
        panel = Panel(transport)
        panel.init()
        panel.write_frame(frame)
        refresh = panel.refresh()
        panel.power_off()
        panel.sleep()
        return {"refresh": refresh, "refresh_count": panel.refresh_count,
                "busy_records": panel.busy_records, "software_completed": True,
                "hardware_status": "INCONCLUSIVE" if hardware else "NOT RUN"}
    finally:
        try:
            if panel is not None:
                panel.close()
        finally:
            if hardware:
                signal.setitimer(signal.ITIMER_REAL, 0)
                for sig, old in handlers.items():
                    signal.signal(sig, old)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "dry-run", "mock", "smoke"))
    parser.add_argument("--pattern", choices=PATTERNS + ("smoke",), default="smoke")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inspection", type=Path)
    parser.add_argument("--sample-busy", action="store_true", help="preflight: claim BUSY as input only")
    parser.add_argument("--speed-hz", type=int, default=100_000)
    parser.add_argument("--busy-timeout", type=float, default=20)
    parser.add_argument("--deadline", type=float, default=60)
    parser.add_argument("--rotation", type=int, default=0)
    parser.add_argument("--swap-cs", action="store_true")
    parser.add_argument("--resistor", choices=("3", "0.47"), default="3", help="record physical selector; never changes it")
    args = parser.parse_args(argv)
    config = Config(speed_hz=args.speed_hz, busy_timeout=args.busy_timeout,
                    deadline=args.deadline, rotation=args.rotation, swap_cs=args.swap_cs,
                    resistor=args.resistor)
    try:
        config.validate()
        if args.command == "preflight":
            result = inventory(config, sample_busy=args.sample_busy)
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                save_json(args.output / "preflight.json", result)
            print(json.dumps(result, indent=2))
            return 1 if "FAIL" in result["checks"].values() else 0
        run_id = datetime.now(TIMEZONE).strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(3).hex()
        directory = args.output or Path(os.environ.get("XDG_STATE_HOME", Path.home()/".local/state")) / "eink-driver" / run_id
        directory.mkdir(parents=True, exist_ok=False)
        result = {"run_id": run_id, "started": timestamp(), "mode": args.command,
                  "config": config.record(), "code_version": code_version(),
                  "hardware_status": "NOT RUN", "software_completed": False}
        save_json(directory / "result.json", result)
        frame = render_artifacts(directory, args.pattern, run_id, config)
        try:
            if args.command == "smoke":
                result["inspection"] = validate_inspection(args.inspection, config)
                result["preflight"] = inventory(config)
                if "FAIL" in result["preflight"]["checks"].values():
                    raise ValueError("Preflight failed; panel not energized")
            if args.command in ("mock", "smoke"):
                with (directory / "events.jsonl").open("w", buffering=1) as events:
                    def emit(event, **fields):
                        events.write(json.dumps({"time": timestamp(), "event": event, **fields}) + "\n")
                    result.update(execute_refresh(config, frame, emit, args.command == "smoke"))
            else:
                result["software_completed"] = True
            result["finished"] = timestamp()
            save_json(directory / "result.json", result)
            print(json.dumps({"output": str(directory), "mode": args.command,
                              "hardware_status": result["hardware_status"]}))
            return 0
        except BaseException as exc:
            result.update(error=str(exc), finished=timestamp())
            save_json(directory / "result.json", result)
            raise
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({"error": str(exc), "hardware_status": "INCONCLUSIVE"}))
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
