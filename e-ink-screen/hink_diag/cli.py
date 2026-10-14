import argparse
import json
import signal
import sys
from pathlib import Path

from .artifacts import ROOT, Run, VISUAL_FIELDS, apply_observations, code_version, compare, evaluate_observation, save_json
from .config import Config, PINS
from .images import PATTERNS, pack, pattern, reconstruct, split_rows
from .panel import BusyNotObserved, Panel
from .preflight import inventory
from .transport import Budget, DeadlineExceeded, FakeClock, live_transport, mock_transport


class Blocked(RuntimeError):
    pass


def hardware_gate(args, config, run):
    if config.resistor == "0.47":
        raise Blocked("0.47 ohm execution blocked: no adapter schematic or exact-panel RESE/booster evidence")
    if not args.inspection:
        raise Blocked("Powered-off wiring/ribbon inspection and explicit 3 ohm confirmation required")
    inspection=json.loads(Path(args.inspection).read_text())
    required=("all_power_disconnected_during_inspection","ribbon_seated_contacts_checked",
              "wiring_matches_table","fan_preserved","no_visible_damage","no_abnormal_heating")
    if not all(inspection.get(k) is True for k in required) or inspection.get("resistor")!=config.resistor:
        raise Blocked("Inspection incomplete, damage/heating noted, or selector confirmation mismatched")
    if not inspection.get("confirmed_at") or not inspection.get("observer"):
        raise Blocked("Inspection needs dated observer confirmation")
    run.data["inspection"]=inspection
    run.data["ambient"]=inspection.get("ambient",{})
    run.data["starting_image"]=inspection.get("starting_image")
    preflight=inventory(config)
    run.data["preflight"]=preflight
    if any(v=="FAIL" for v in preflight["checks"].values()):
        raise Blocked("Hardware preflight failed; inspect saved inventory before energizing")
    if args.command in ("functional","benchmark"):
        if not args.smoke_run:
            raise Blocked("Functional tests require an observed hardware smoke PASS")
        smoke=json.loads((Path(args.smoke_run)/"result.json").read_text())
        if smoke["mode"]!="hardware" or smoke["kind"]!="smoke" or smoke["status"]!="PASS":
            raise Blocked("Smoke has no verified new whole-screen image PASS")
        if smoke["code_version"]["sha256"]!=run.data["code_version"]["sha256"] or smoke["config"]!=config.record():
            raise Blocked("Smoke revision/config mismatch; repeat smoke with these settings")
        run.data["smoke_run_id"]=smoke["run_id"]
        if args.command=="functional" and not sys.stdin.isatty():
            raise Blocked("Hardware functional sequence requires interactive per-image observations in tmux")


def save_image(run, name, image):
    directory=run.path/"patterns";directory.mkdir(exist_ok=True)
    image.save(directory/f"{name}.png")
    frame=pack(image);left,right=split_rows(frame)
    (directory/f"{name}.frame.bin").write_bytes(frame)
    (directory/f"{name}.cs1.bin").write_bytes(right if run.data["config"]["swap_cs"] else left)
    (directory/f"{name}.cs2.bin").write_bytes(left if run.data["config"]["swap_cs"] else right)
    reconstruct(left,right).save(directory/f"{name}.reconstructed.png")
    return frame


def observe_interactively(run, name):
    print(f"Observe {name}, expected PNG in {run.path}/patterns. Check heat/supply first.")
    observation={}
    for field in VISUAL_FIELDS:
        answer=input(f"{field}? [yes/no/unknown]: ").strip().lower()
        observation[field]=True if answer=="yes" else False if answer=="no" else None
        if answer!="yes":
            run.data["observations"].setdefault("steps",{})[name]=observation
            return observation
    for field in ("contrast","ghosting","controller_seam","image_completeness"):
        observation[field]=input(f"{field} observation: ").strip() or None
    run.data["observations"].setdefault("steps",{})[name]=observation
    return observation


def execute(args, config, run):
    mode=run.data["mode"]
    if mode=="hardware":hardware_gate(args,config,run)
    budget=Budget(config.deadline,FakeClock() if mode=="mock" else None)
    transport=None; panel=None
    previous={}
    def interrupt(signum, frame):
        if signum==signal.SIGALRM:raise DeadlineExceeded("Overall wall-clock deadline exceeded")
        raise KeyboardInterrupt(f"Interrupted by signal {signum}")
    if mode=="hardware":
        for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM):
            previous[sig]=signal.signal(sig,interrupt)
        signal.setitimer(signal.ITIMER_REAL,config.deadline)
    try:
        if args.command=="signals":
            if mode=="hardware":transport=live_transport(config,budget,run.emit)
            elif mode=="mock":transport=mock_transport(config,budget,run.emit)
            if transport:
                # CS remain HIGH during SPI clock/MOSI activity. No controller commands.
                transport.deselect()
                for dc in (0,1):
                    transport.gpio.write(PINS["dc"],dc)
                    budget.sleep(0.05)
                transport.spi.writebytes2(bytes.fromhex("aa 55 00 ff")*4)
                # Exercise selects independently WITHOUT clocks; never assert both here.
                for target in ("cs1","cs2"):
                    transport.gpio.write(PINS[target],0);budget.sleep(0.05)
                    transport.gpio.write(PINS[target],1);budget.sleep(0.05)
                levels=[]
                for _ in range(100):
                    levels.append(transport.busy());budget.sleep(0.005)
                run.data["busy_samples"]=levels
            run.data["status"]="INCONCLUSIVE" if mode=="hardware" else "PASS" if mode=="mock" else "NOT RUN"
            return
        names=tuple(f"burst-{i+1}" for i in range(args.frames)) if args.command=="benchmark" else ("desktop",) if args.command=="desktop" else ("smoke",) if args.command=="smoke" else PATTERNS
        # Artifacts exist even when mock/live test fails at first initialization.
        frames={}
        for i,n in enumerate(names):
            if args.command=="desktop":
                import shutil
                from .desktop import capture,convert
                source=run.path/"source-desktop.png"
                if args.image:
                    shutil.copy2(args.image,source)
                    run.data["capture"]={"method":"supplied image","path":str(args.image)}
                elif mode=="hardware":run.data["capture"]=capture(source)
                else:raise Blocked("Dry-run/mock desktop requires --image; no implicit capture")
                image,metadata=convert(source,run.id,config.rotation,args.dither)
                run.data["desktop"]=metadata
                frames[n]=save_image(run,n,image)
                continue
            image=pattern("diagnostic" if args.command=="benchmark" else n,
                          f"{run.id} {i+1}/{len(names)}" if args.command=="benchmark" else run.id,config.rotation)
            if args.command=="benchmark" and i%2:
                image=image.point(lambda pixel:255-pixel)
            frames[n]=save_image(run,n,image)
        completions=[]
        run.data["steps"]=[{"name":n,"status":"NOT RUN","software_completed":False} for n in names]
        run.save()
        if mode=="dry-run":
            run.emit("dry_run",spi_opened=False,gpio_claimed=False,refresh_commands_sent=0)
            return
        if mode=="hardware":transport=live_transport(config,budget,run.emit)
        elif mode=="mock":transport=mock_transport(config,budget,run.emit)
        panel=Panel(transport)
        panel.init()
        for step in run.data["steps"]:
            name=step["name"]
            if name=="wake":
                panel.sleep();run.emit("sleep_wake",state="sleeping")
                budget.sleep(1.0);panel.init()
            try:
                cycle_start=budget.clock.now()
                panel.write_frame(frames[name])
                upload_end=budget.clock.now()
                record=panel.refresh()
                complete=budget.clock.now()
                completions.append(complete)
                if args.command=="benchmark":
                    step.update(upload_seconds=upload_end-cycle_start,
                                cycle_seconds=complete-cycle_start,
                                completion_monotonic_seconds=complete)
                    print(f"{name}: upload {upload_end-cycle_start:.4f}s; BUSY {record['duration_seconds']:.4f}s; cycle {complete-cycle_start:.4f}s",flush=True)
                step.update(software_completed=True,refresh_seconds=record["duration_seconds"],
                            busy_active_observed=record["active_observed"],
                            status="PASS" if mode=="mock" else "INCONCLUSIVE")
                # Keep high-voltage generation off during spacing and manual observation.
                if args.command!="benchmark":panel.power_off()
                if mode=="hardware" and args.command=="functional":
                    observation=observe_interactively(run,name)
                    step["status"]=evaluate_observation(observation)
                    run.save()
                    if step["status"]!="PASS":
                        raise Blocked("Physical observation failed/inconclusive; stop sequence and investigate")
            except BaseException as exc:
                if not step["software_completed"]:
                    step["status"]="INCONCLUSIVE" if isinstance(exc,BusyNotObserved) else "FAIL"
                step["error"]=str(exc)
                raise
            finally:
                run.save()
        run.data["status"]="PASS" if mode=="mock" else "INCONCLUSIVE"
        run.data["refresh_count"]=panel.refresh_count
        if args.command=="benchmark":
            interval=(completions[-1]-completions[0])/(len(completions)-1)
            run.data["benchmark"]={"frames":len(completions),
                "mean_completion_interval_seconds":interval,
                "observed_full_frame_rate_hz":1/interval,
                "busy_only_upper_bound_hz":1/min(s["refresh_seconds"] for s in run.data["steps"]),
                "booster_kept_on_between_frames":True,
                "continuous_operation_validated":False,
                "physical_spi_clock_measured":False}
            import csv
            with (run.path/"benchmark.csv").open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=("name","upload_seconds","refresh_seconds","cycle_seconds"));w.writeheader()
                for s in run.data["steps"]:w.writerow({k:s[k] for k in w.fieldnames})
            print(f"Observed full-frame rate: {1/interval:.4f} Hz ({interval:.4f} s/frame)",flush=True)
    except BaseException:
        if panel:panel.abort()
        raise
    finally:
        try:
            if panel:
                run.data["refresh_count"]=panel.refresh_count
                run.data["busy_records"]=panel.busy_records
                panel.close()
            elif transport:transport.close()
        finally:
            if previous:
                signal.setitimer(signal.ITIMER_REAL,0)
                for sig,handler in previous.items():signal.signal(sig,handler)
        run.emit("cleanup",physical_power_removed=False,
                 normal_sleep=bool(panel and not panel.powered))


def parser():
    p=argparse.ArgumentParser(description="Bounded exact-panel diagnostics; default is dry-run")
    sub=p.add_subparsers(dest="command",required=True)
    for name in ("preflight","signals","smoke","functional","benchmark","desktop","comparison"):
        s=sub.add_parser(name)
        mode=s.add_mutually_exclusive_group()
        mode.add_argument("--hardware",action="store_true")
        mode.add_argument("--mock",action="store_true")
        s.add_argument("--resistor",choices=("3","0.47"),default="3",help="Physical selector record only")
        s.add_argument("--runs",default="runs")
        s.add_argument("--run-id")
        s.add_argument("--spi-path",default="/dev/spidev0.0")
        s.add_argument("--speed-hz",type=int,default=100_000)
        s.add_argument("--busy-timeout",type=float,default=20)
        s.add_argument("--deadline",type=float,default=1800)
        s.add_argument("--spacing",type=float,default=180)
        s.add_argument("--rotation",type=int,choices=(0,90,180,270),default=0)
        s.add_argument("--swap-cs",action="store_true")
        s.add_argument("--inspection",help="Dated physical confirmation JSON")
        s.add_argument("--smoke-run",help="Observed smoke PASS directory for hardware functional test")
        if name=="desktop":
            s.add_argument("--image",help="Existing screenshot; otherwise capture live Wayland desktop only in hardware mode")
            s.add_argument("--dither",choices=("floyd-steinberg","threshold"),default="floyd-steinberg")
        if name=="benchmark":
            s.add_argument("--frames",type=int,choices=(2,3),default=3,help="Bounded burst, no retries")
        if name=="preflight":
            s.add_argument("--sample-busy",action="store_true",help="Claim BUSY as input briefly; no output/reset/SPI")
    a=sub.add_parser("annotate");a.add_argument("run");a.add_argument("observations")
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    if args.command=="annotate":
        data=apply_observations(args.run,args.observations)
        compare(Path(args.run).parent)
        print(f"{data['run_id']}: {data['status']}")
        return 0
    config=Config(spi_path=args.spi_path,speed_hz=args.speed_hz,busy_timeout=args.busy_timeout,
                  deadline=args.deadline,spacing=args.spacing,rotation=args.rotation,
                  swap_cs=args.swap_cs,resistor=args.resistor)
    config.validate()
    if args.command=="benchmark" and config.spacing!=0:
        raise ValueError("Benchmark requires explicit --spacing 0")
    Path(args.runs).mkdir(parents=True,exist_ok=True)
    if args.command=="comparison":
        for row in compare(args.runs):print(f"{row['resistor']} ohm | {row['check']} | {row['status']}")
        return 0
    mode="hardware" if args.hardware else "mock" if args.mock else "dry-run"
    run=Run(args.runs,config,mode,args.command,args.run_id)
    exit_code=0
    try:
        if args.command=="preflight":
            # Read-only inventory on any host, including default dry-run.
            run.data["preflight"]=inventory(config,sample_busy=args.sample_busy)
            checks=run.data["preflight"]["checks"]
            run.data["status"]="FAIL" if "FAIL" in checks.values() else "PASS"
            exit_code=1 if run.data["status"]=="FAIL" else 0
        else:
            execute(args,config,run)
    except (Blocked,BusyNotObserved) as exc:
        run.data["status"]="NOT RUN" if isinstance(exc,Blocked) and not run.data["steps"] else "INCONCLUSIVE"
        run.data["execution_blocked"]=True
        run.data["blocked_reason"]=str(exc)
        run.data["errors"].append(str(exc))
        run.emit("blocked",reason=str(exc));exit_code=2
    except BaseException as exc:
        run.data["status"]="FAIL"
        run.data["errors"].append(f"{type(exc).__name__}: {exc}")
        run.emit("failure",error=str(exc));exit_code=130 if isinstance(exc,KeyboardInterrupt) else 1
    finally:
        run.finish();compare(args.runs)
    print(f"{run.id}: {run.data['status']} ({mode}); artifacts {run.path}")
    if run.data["errors"]:print(run.data["errors"][-1],file=sys.stderr)
    return exit_code


if __name__=="__main__":
    raise SystemExit(main())
