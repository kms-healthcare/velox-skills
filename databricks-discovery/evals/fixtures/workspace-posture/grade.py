"""python3 grade.py <run dir>/posture.json [answer-key.json] — recall over expected failures, precision over reported ones."""
import json
import sys
from pathlib import Path

posture = json.loads(Path(sys.argv[1]).read_text())
key = json.loads(Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).with_name("answer-key.json")).read_text())
failed = {c["check_id"] for c in posture["checks"] if c["status"] == "fail"}
expected = set(key["expected_fail"])
# a run fed SAT results is expected to surface SAT's own failures too
if any(c["source"] == "sat" for c in posture["checks"]):
    expected |= set(key.get("expected_fail_from_sat", {}).get("checks", []))
hit, missed, extra = failed & expected, expected - failed, failed - expected
print(f"recall {len(hit)}/{len(expected)} = {len(hit) / len(expected):.0%} · precision {len(hit)}/{len(failed) or 1} = "
      f"{len(hit) / (len(failed) or 1):.0%} · score {posture['score']} / 5")
for c in sorted(missed):
    print(f"  missed  {c:<9} {key['expected_fail'][c]}")
for c in sorted(extra):
    print(f"  extra   {c:<9} {key.get('expected_not_failing', {}).get(c, 'not in the answer key')}")
