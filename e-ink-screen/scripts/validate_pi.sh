#!/bin/bash
set -uo pipefail
mkdir -p evidence/software
python3 -m unittest discover -v 2>&1 | tee evidence/software/unittest-pi.log
tests_status=${PIPESTATUS[0]}
python3 scripts/reference_oracle.py evidence/software/pi-reference 2>&1 | tee evidence/software/reference-pi.log
reference_status=${PIPESTATUS[0]}
python3 -m hink_diag smoke --mock --runs runs
smoke_status=$?
python3 -m hink_diag functional --mock --runs runs
functional_status=$?
python3 -m hink_diag functional --mock --resistor 0.47 --runs runs
comparison_status=$?
python3 -m hink_diag preflight --hardware --sample-busy --runs runs
preflight_status=$?
python3 - "$tests_status" "$reference_status" "$smoke_status" "$functional_status" "$comparison_status" "$preflight_status" <<'PY'
import json,sys
from pathlib import Path
from hink_diag.artifacts import timestamp,code_version
checks=dict(zip(("unit_tests","reference_oracle","mock_smoke","mock_functional_3","mock_functional_047","hardware_readonly_preflight"),map(int,sys.argv[1:])))
result={"time":timestamp(),"checks":checks,"code_version":code_version(),"hardware_refreshes":0}
Path("evidence/software/pi-validation.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result["checks"],indent=2))
PY
test "$tests_status" -eq 0 && test "$reference_status" -eq 0 && test "$smoke_status" -eq 0 && test "$functional_status" -eq 0 && test "$comparison_status" -eq 0
