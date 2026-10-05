#!/usr/bin/env bash
# Plant two misconfigurations in the TEST workspace so security-posture has known answers to find.
# Run by a person, never by the agent; `unplant` reverses both. Usage: ./plant.sh [plant|unplant] [profile]
set -euo pipefail
action=${1:-plant}; profile=${2:-DEFAULT}
db=${DATABRICKS_CLI:-databricks}
schema=eurostream.gold
job=308918004912379   # [dev hieunle] eurostream_fraud
case "$action" in
  plant)
    # P-1 → VX-UC-1: every user may write and manage the gold schema
    "$db" grants update schema "$schema" -p "$profile" \
      --json '{"changes":[{"principal":"account users","add":["ALL_PRIVILEGES"]}]}' >/dev/null
    # P-2 → GOV-45: every user may manage (edit, run as, delete) a production job
    "$db" permissions update jobs "$job" -p "$profile" \
      --json '{"access_control_list":[{"group_name":"users","permission_level":"CAN_MANAGE"}]}' >/dev/null
    echo "planted P-1 (grant on $schema) and P-2 (CAN_MANAGE on job $job)";;
  unplant)
    "$db" grants update schema "$schema" -p "$profile" \
      --json '{"changes":[{"principal":"account users","remove":["ALL_PRIVILEGES"]}]}' >/dev/null
    acl=$("$db" permissions get jobs "$job" -p "$profile" -o json | python3 -c '
import json, sys
acl = json.load(sys.stdin).get("access_control_list", [])
keep = []
for a in acl:
    if a.get("group_name") == "users":
        continue
    lv = [p["permission_level"] for p in a.get("all_permissions", []) if not p.get("inherited")]
    if lv:
        who = {k: a[k] for k in ("user_name", "group_name", "service_principal_name") if k in a}
        keep.append({**who, "permission_level": lv[0]})
print(json.dumps({"access_control_list": keep}))')
    "$db" permissions set jobs "$job" -p "$profile" --json "$acl" >/dev/null
    echo "removed P-1 and P-2";;
  *) echo "usage: $0 [plant|unplant] [profile]" >&2; exit 2;;
esac
