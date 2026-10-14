import csv
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TIMEZONE = ZoneInfo("Asia/Shanghai")


def timestamp():
    return datetime.now(TIMEZONE).isoformat(timespec="milliseconds")


def code_version():
    files = sorted(list((ROOT/"hink_diag").glob("*.py")) + list((ROOT/"scripts").glob("*.py"))
                   + list((ROOT/"tests").glob("*.py")) + [ROOT/"pyproject.toml"]
                   + list((ROOT/"evidence/upstream").glob("*.cpp"))
                   + list((ROOT/"evidence/upstream").glob("*.h")))
    manifest = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    digest = hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    return {"sha256":digest,"manifest":manifest}


def save_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")
    temporary.replace(path)


class Run:
    def __init__(self, directory, config, mode, kind, run_id=None):
        import uuid
        self.id = run_id or (datetime.now(TIMEZONE).strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:6])
        self.path = Path(directory)/self.id
        self.path.mkdir(parents=True,exist_ok=False)
        self.log = (self.path/"events.jsonl").open("a",buffering=1)
        self.data = {"run_id":self.id,"started":timestamp(),"kind":kind,"mode":mode,
                     "config":config.record(),"code_version":code_version(),
                     "steps":[],"errors":[],"status":"NOT RUN", "measurements":{},
                     "retention":"NOT RUN", "photos":[], "observations":{}}
        import platform, sys
        self.data["runtime"]={"python":sys.version,"platform":platform.platform(),"argv":sys.argv}
        self.save()

    def emit(self, event, **fields):
        self.log.write(json.dumps({"time":timestamp(),"event":event,**fields})+"\n")

    def save(self):
        save_json(self.path/"result.json",self.data)
        with (self.path/"results.csv").open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=("run_id","resistor","mode","step","status","refresh_seconds","busy_active_observed","error"))
            writer.writeheader()
            for step in self.data["steps"]:
                writer.writerow({"run_id":self.id,"resistor":self.data["config"]["resistor"],
                                 "mode":self.data["mode"],"step":step["name"],"status":step["status"],
                                 "refresh_seconds":step.get("refresh_seconds"),
                                 "busy_active_observed":step.get("busy_active_observed"),"error":step.get("error")})

    def finish(self):
        self.data["finished"]=timestamp()
        self.save()
        self.log.close()


VISUAL_FIELDS = ("new_image", "whole_screen", "orientation", "both_halves", "matches_expected", "no_abnormal_heating", "no_supply_problems_observed")


def evaluate_observation(observation):
    if any(observation.get(k) is False for k in VISUAL_FIELDS):
        return "FAIL"
    if all(observation.get(k) is True for k in VISUAL_FIELDS):
        return "PASS"
    return "INCONCLUSIVE"


def apply_observations(run_path, observation_path):
    run_path=Path(run_path)
    result=run_path/"result.json"
    data=json.loads(result.read_text())
    if data["mode"] != "hardware":
        raise ValueError("Mock/dry-run evidence cannot acquire hardware PASS")
    observations=json.loads(Path(observation_path).read_text())
    if observations.get("run_id")!=data["run_id"]:
        raise ValueError("Observation run ID mismatch")
    save_json(run_path/"manual-observations.json",observations)
    data["observations"]=observations
    for step in data["steps"]:
        if step.get("software_completed"):
            step["status"]=evaluate_observation(observations.get("steps",{}).get(step["name"],{}))
    retention=observations.get("retention",{})
    if retention.get("all_power_disconnected") is True and retention.get("new_image_retained") is True:
        data["retention"]="PASS"
    elif retention.get("new_image_retained") is False:
        data["retention"]="FAIL"
    else:
        data["retention"]="INCONCLUSIVE"
    data["measurements"]=observations.get("measurements",{})
    for supplied in observations.get("photos",[]):
        source=Path(supplied)
        if not source.is_absolute():source=Path(observation_path).resolve().parent/source
        photo_dir=run_path/"photos";photo_dir.mkdir(exist_ok=True)
        target=photo_dir/source.name
        shutil.copy2(source,target)
        data["photos"].append(str(target.relative_to(run_path)))
    required = [s["name"] for s in data["steps"]] if data["kind"] in ("benchmark","desktop") else ["smoke"] if data["kind"]=="smoke" else ["white","black","halves","halves-swapped","diagnostic","wake"]
    statuses={s["name"]:s["status"] for s in data["steps"]}
    if data["errors"] or "FAIL" in statuses.values() or data["retention"]=="FAIL":
        data["status"]="FAIL"
    elif all(statuses.get(n)=="PASS" for n in required) and (data["kind"] in ("smoke","benchmark","desktop") or data["retention"]=="PASS"):
        data["status"]="PASS"
    else:
        data["status"]="INCONCLUSIVE"
    save_json(result,data)
    # Regenerate CSV using the same schema after annotations.
    with (run_path/"results.csv").open("w",newline="") as f:
        fields=("run_id","resistor","mode","step","status","refresh_seconds","busy_active_observed","error")
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for s in data["steps"]:
            writer.writerow({"run_id":data["run_id"],"resistor":data["config"]["resistor"],"mode":data["mode"],
                             "step":s["name"],"status":s["status"],"refresh_seconds":s.get("refresh_seconds"),
                             "busy_active_observed":s.get("busy_active_observed"),"error":s.get("error")})
    return data


def compare(directory):
    directory=Path(directory)
    checks=("smoke","white","black","halves","halves-swapped","diagnostic","wake","retention","system")
    rows=[]
    candidates=[]
    for p in sorted(directory.glob("*/result.json")):
        data=json.loads(p.read_text())
        if data["mode"]=="hardware" and data["kind"] in ("smoke","functional"):
            candidates.append(data)
    selected={}
    for setting in ("3","0.47"):
        runs=[d for d in candidates if d["config"]["resistor"]==setting]
        # Select latest run per kind; never merge checks from unrelated functional attempts.
        smoke=next((d for d in reversed(runs) if d["kind"]=="smoke"),None)
        functional=next((d for d in reversed(runs) if d["kind"]=="functional"),None)
        selected[setting]={"smoke":smoke,"functional":functional}
        for check in checks:
            data=smoke if check=="smoke" else functional
            status="NOT RUN"
            if data:
                if check=="system":status=data["status"]
                elif check=="retention":status=data["retention"]
                else:status=next((s["status"] for s in data["steps"] if s["name"]==check),"NOT RUN")
            rows.append({"resistor":setting,"check":check,"status":status,
                         "run_id":data["run_id"] if data else None,
                         "execution_blocked":setting=="0.47",
                         "reason":"No adapter schematic or exact-panel validation for 0.47 ohm" if setting=="0.47" else ""})
    with (directory/"comparison.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    a,b=(selected[s]["functional"] for s in ("3","0.47"))
    matched=False
    if a and b:
        ca,cb=({k:v for k,v in d["config"].items() if k!="resistor"} for d in (a,b))
        matched=(ca==cb and a["code_version"]["sha256"]==b["code_version"]["sha256"]
                 and a.get("starting_image") is not None and a.get("starting_image")==b.get("starting_image")
                 and bool(a.get("ambient")) and a.get("ambient")==b.get("ambient"))
    summary={s:{"functional_run":d["functional"]["run_id"] if d["functional"] else None,
                "measurements":d["functional"].get("measurements",{}) if d["functional"] else {},
                "steps":d["functional"]["steps"] if d["functional"] else [],
                "observations":d["functional"].get("observations",{}) if d["functional"] else {}}
             for s,d in selected.items()}
    save_json(directory/"comparison.json",{"checks":rows,"settings":summary,
              "comparison_valid":bool(matched and a["status"]==b["status"]=="PASS"),
              "conditions_matched":matched,
              "note":"Compare only matched revision/settings/start image/ambient; measurements absent unless supplied."})
    lines=["| Check | 3 Ω | 0.47 Ω |","|---|---|---|"]
    for c in checks:
        lines.append("| "+c+" | "+" | ".join(next(r["status"] for r in rows if r["check"]==c and r["resistor"]==s) for s in ("3","0.47"))+" |")
    (directory/"comparison.md").write_text("\n".join(lines)+"\n\n0.47 Ω execution blocked: no defensible adapter/panel evidence.\n")
    return rows
