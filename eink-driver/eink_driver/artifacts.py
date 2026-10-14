"""Installation-independent code hashes and atomic JSON artifacts."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
TIMEZONE = ZoneInfo("Asia/Shanghai")


def timestamp():
    return datetime.now(TIMEZONE).isoformat(timespec="milliseconds")


def code_version():
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and
                   (p.suffix in (".py", ".cpp", ".h", ".md", ".json") or p.name == "LICENSE"))
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "manifest": manifest}


def save_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)
