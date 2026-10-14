"""Atomic run metadata and installed runtime source fingerprints."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import eink_driver

def timestamp():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="milliseconds")

def save_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)

def code_version():
    manifest = {}
    for name, directory in (("bitcoin_eink", Path(__file__).parent), ("eink_driver", Path(eink_driver.__file__).parent)):
        for source in sorted(directory.glob("*.py")):
            manifest[f"{name}/{source.name}"] = hashlib.sha256(source.read_bytes()).hexdigest()
    return {"sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(), "manifest": manifest}
