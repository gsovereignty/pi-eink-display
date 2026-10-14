import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hink_diag.artifacts import VISUAL_FIELDS,apply_observations
from hink_diag.cli import main


class CliTest(unittest.TestCase):
    def test_imports_no_hardware_or_refresh(self):
        code='''
import builtins
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name in ("lgpio","spidev"):raise AssertionError("Hardware library imported")
    return original(name,*args,**kwargs)
builtins.__import__=guarded
import hink_diag, hink_diag.images, hink_diag.panel, hink_diag.cli
'''
        subprocess.run([sys.executable,"-c",code],check=True,timeout=5)

    def test_dry_run_has_artifacts_and_no_transport(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("hink_diag.cli.live_transport") as live,patch("hink_diag.cli.mock_transport") as mock:
            self.assertEqual(main(["functional","--runs",directory,"--run-id","dry-test"]),0)
            live.assert_not_called();mock.assert_not_called()
            result=json.loads((Path(directory)/"dry-test/result.json").read_text())
            self.assertEqual(result["status"],"NOT RUN")
            self.assertTrue(all(s["status"]=="NOT RUN" for s in result["steps"]))
            for name in ("white","black","halves","halves-swapped","diagnostic","wake"):
                frame=Path(directory)/f"dry-test/patterns/{name}.frame.bin"
                self.assertEqual(frame.stat().st_size,15000)

    def test_preflight_never_opens_transport(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("hink_diag.cli.inventory",return_value={"checks":{"spi":"FAIL"}}), \
             patch("hink_diag.cli.live_transport") as live:
            self.assertEqual(main(["preflight","--hardware","--runs",directory]),1)
            live.assert_not_called()

    def test_047_hardware_blocked_before_gpio(self):
        with tempfile.TemporaryDirectory() as directory,patch("hink_diag.cli.live_transport") as live:
            self.assertEqual(main(["smoke","--hardware","--resistor","0.47","--runs",directory]),2)
            live.assert_not_called()

    def test_3_hardware_needs_inspection_before_gpio(self):
        with tempfile.TemporaryDirectory() as directory,patch("hink_diag.cli.live_transport") as live:
            self.assertEqual(main(["smoke","--hardware","--runs",directory]),2)
            live.assert_not_called()

    def test_mock_failure_aborts_remaining_sequence(self):
        from hink_diag.transport import mock_transport
        def broken(c,b,e):
            t=mock_transport(c,b,e);t.spi.fail_at=30;return t
        with tempfile.TemporaryDirectory() as directory,patch("hink_diag.cli.mock_transport",side_effect=broken):
            self.assertEqual(main(["functional","--mock","--runs",directory,"--run-id","fault"]),1)
            d=json.loads((Path(directory)/"fault/result.json").read_text())
            self.assertEqual(d["status"],"FAIL")
            self.assertFalse(any(s["software_completed"] for s in d["steps"]))
            self.assertEqual(d["refresh_count"],0)

    def test_mock_cannot_be_annotated_as_hardware_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            main(["smoke","--mock","--runs",directory,"--run-id","mock"])
            observation=Path(directory)/"observation.json"
            observation.write_text(json.dumps({"run_id":"mock","steps":{"smoke":{k:True for k in VISUAL_FIELDS}}}))
            with self.assertRaises(ValueError):apply_observations(Path(directory)/"mock",observation)

    def test_partial_observation_never_passes(self):
        from hink_diag.artifacts import evaluate_observation
        self.assertEqual(evaluate_observation({"new_image":True}),"INCONCLUSIVE")
        self.assertEqual(evaluate_observation({"new_image":False}),"FAIL")

    def test_fake_runs_do_not_enter_comparison(self):
        with tempfile.TemporaryDirectory() as directory:
            main(["smoke","--mock","--runs",directory,"--run-id","m3"])
            main(["smoke","--mock","--resistor","0.47","--runs",directory,"--run-id","m047"])
            d=json.loads((Path(directory)/"comparison.json").read_text())
            self.assertTrue(all(r["status"]=="NOT RUN" for r in d["checks"]))
