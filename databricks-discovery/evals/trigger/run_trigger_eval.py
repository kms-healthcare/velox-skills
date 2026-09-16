#!/usr/bin/env python3
"""Trigger evaluation for a skill description — hardened fork of skill-creator's run_eval.py.

  python3 run_trigger_eval.py --eval-set <set.json> --skill-name <name> --description-file <f.txt>
                              [--model M] [--runs-per-query N] [--num-workers N] [--timeout S]

Why a fork. The upstream runner reported 0/10 recall on a description that had previously
scored 56%, because it cannot tell these three apart:

  * the child answered in prose and called no tool at all
  * the child errored (spend limit, auth) — stderr went to DEVNULL, the error text
    arrived as an ordinary assistant message
  * the child genuinely considered the skill and declined it

All three became `triggered = False`, so a broken run and a bad description look identical.
It also returned False the moment the FIRST tool call was not Skill/Read — a child that opens
with TodoWrite scored a false negative — and gave every parallel worker its own temp skill
file, so several near-identical skills were visible at once and a child could pick a sibling.

This version records a per-run OUTCOME, creates ONE temp skill for the whole arm, keeps
stderr, and refuses to report a score when the run did not measure anything.
"""
import argparse, json, os, re, select, subprocess, sys, tempfile, time, uuid
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Text a child emits when the run never really happened. Matched against assistant prose,
# which is where `claude -p` puts them — they never reach stderr.
FATAL = [
    (r"monthly spend limit|usage limit|rate limit", "spend-or-rate-limit"),
    (r"Invalid API key|authentication_error|please run /login", "auth"),
    (r"model .* (not found|not available)|invalid model", "bad-model"),
    (r"Credit balance is too low", "billing"),
]
TRIGGER_TOOLS = ("Skill", "Read", "SlashCommand")
# Reaching for one of these before the skill means the child started the work without it — that
# is a real no-trigger and we can stop reading. Planning tools (TodoWrite) and Read decide nothing:
# a child that opens with a todo list and then invokes the skill has triggered.
DECISIVE_WORK_TOOLS = ("Bash", "Write", "Edit", "NotebookEdit", "Task", "WebFetch", "WebSearch", "Glob", "Grep")


def find_project_root() -> Path:
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / ".claude").is_dir():
            return p
    return Path.cwd()


def run_single_query(query, clean_name, timeout, cwd, model, plugin_dir=None, sys_prompt=None):
    """Return (outcome, detail). Outcome is one of:
    triggered · no_tool · other_tool_only · error · timeout · empty_stream"""
    cmd = ["claude", "-p", query, "--output-format", "stream-json", "--verbose",
           "--include-partial-messages"]
    if model:
        cmd += ["--model", model]
    if plugin_dir:
        cmd += ["--plugin-dir", plugin_dir]
    if sys_prompt:
        cmd += ["--append-system-prompt", sys_prompt]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=cwd, env=env)

    buf, text, tools, events = "", [], [], 0
    pending, acc, first_turn_done = None, "", False
    start = time.time()
    try:
        while time.time() - start < timeout and not first_turn_done:
            if proc.poll() is not None:
                rest = proc.stdout.read()
                if rest:
                    buf += rest.decode("utf-8", "replace")
                first_turn_done = True
            else:
                ready, _, _ = select.select([proc.stdout], [], [], 1.0)
                if not ready:
                    continue
                chunk = os.read(proc.stdout.fileno(), 8192)
                if not chunk:
                    first_turn_done = True
                else:
                    buf += chunk.decode("utf-8", "replace")

            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events += 1

                # Decide from the partial stream, so the child can be killed as soon as the
                # model commits to a tool instead of running the whole task. Unlike upstream,
                # a non-matching tool does NOT end the scan — it resets the accumulator and we
                # keep reading, so a TodoWrite-first child is judged on its whole first turn.
                if e.get("type") == "stream_event":
                    se = e.get("event", {})
                    t = se.get("type", "")
                    if t == "content_block_start":
                        cb = se.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            pending, acc = cb.get("name", "?"), ""
                            tools.append(pending)
                        else:
                            pending = None
                    elif t == "content_block_delta" and pending:
                        d = se.get("delta", {})
                        if d.get("type") == "input_json_delta":
                            acc += d.get("partial_json", "")
                            if pending in TRIGGER_TOOLS and clean_name in acc:
                                return "triggered", pending
                    elif t == "content_block_stop":
                        if pending in TRIGGER_TOOLS and clean_name in acc:
                            return "triggered", pending
                        pending, acc = None, ""
                    if pending in DECISIVE_WORK_TOOLS:
                        return "other_tool_only", pending

                elif e.get("type") == "assistant":
                    for c in e.get("message", {}).get("content", []):
                        if c.get("type") == "tool_use":
                            tools.append(c.get("name", "?"))
                            if c.get("name") in TRIGGER_TOOLS and clean_name in json.dumps(c.get("input", {})):
                                return "triggered", c.get("name")
                            if c.get("name") in DECISIVE_WORK_TOOLS:
                                return "other_tool_only", c.get("name")
                        elif c.get("type") == "text":
                            text.append(c["text"])

                elif e.get("type") == "result":
                    first_turn_done = True

        if not first_turn_done:
            return "timeout", f"no first turn in {timeout}s"
    finally:
        err = b""
        if proc.poll() is None:
            proc.kill()
        try:
            err = proc.stderr.read() or b""
        except Exception:
            pass
        proc.wait()

    joined = " ".join(text) + " " + err.decode("utf-8", "replace")
    for pat, why in FATAL:
        if re.search(pat, joined, re.I):
            return "error", why
    if events == 0:
        return "empty_stream", (err.decode("utf-8", "replace")[:160] or "no events")
    if not tools:
        return "no_tool", "answered in prose"
    return "other_tool_only", ",".join(dict.fromkeys(tools))[:80]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval-set", required=True)
    ap.add_argument("--skill-name", required=True)
    ap.add_argument("--description-file", required=True)
    ap.add_argument("--label", default=None, help="name for this arm in the report")
    ap.add_argument("--num-workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--runs-per-query", type=int, default=3)
    ap.add_argument("--trigger-threshold", type=float, default=0.5)
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-error-rate", type=float, default=0.15,
                    help="above this share of errored runs the arm is reported INVALID")
    ap.add_argument("--out", default=None, help="write the full result JSON here")
    ap.add_argument("--plugin-dir", default=None,
                    help="register the real plugin with --plugin-dir instead of writing a stub skill "
                         "into .claude/commands/. The child then sees the skill exactly as it ships — "
                         "real body, real frontmatter — so the choice it faces is the real one.")
    ap.add_argument("--skill-id", default=None,
                    help="substring that identifies the skill in a Skill tool call (default: --skill-name)")
    ap.add_argument("--child-cwd", default=None,
                    help="working directory for the child runs. In --plugin-dir mode this defaults to a "
                         "scratch dir: once a skill triggers, the child runs the task and WILL write "
                         "files, so it must not be pointed at the repo.")
    ap.add_argument("--append-system-prompt", default=None,
                    help="system-prompt text the real deployment injects (e.g. a check-skills-first norm). "
                         "Without it the child has no reason to prefer a skill over answering directly.")
    a = ap.parse_args()

    eval_set = json.loads(Path(a.eval_set).read_text())
    desc = " ".join(Path(a.description_file).read_text().split())
    root = find_project_root()
    label = a.label or Path(a.description_file).stem

    # ONE temp skill for the whole arm, created here and removed here. Upstream created one
    # per run, so several sibling skills were visible at once and a child could pick a
    # different hash than the one being scored.
    cfile = None
    if a.plugin_dir:
        # The plugin already carries the description under test; nothing to write.
        clean = a.skill_id or a.skill_name
    else:
        clean = f"{a.skill_name}-skill-{uuid.uuid4().hex[:8]}"
        cdir = root / ".claude" / "commands"
        cdir.mkdir(parents=True, exist_ok=True)
        cfile = cdir / f"{clean}.md"
        cfile.write_text("---\ndescription: |\n  " + "\n  ".join(desc.split("\n")) +
                         f"\n---\n\n# {clean}\n\nThis skill handles: {desc}\n")

    # A triggered child does not stop at the decision — it starts doing the work, and this pack's
    # work is "write files". Keep it out of the repo.
    child_cwd = Path(a.child_cwd) if a.child_cwd else (
        Path(tempfile.mkdtemp(prefix="trigger-eval-")) if a.plugin_dir else root)
    child_cwd.mkdir(parents=True, exist_ok=True)
    print(f"child cwd: {child_cwd}", file=sys.stderr)

    runs = {}
    try:
        with ProcessPoolExecutor(max_workers=a.num_workers) as ex:
            fut = {}
            for item in eval_set:
                for _ in range(a.runs_per_query):
                    f = ex.submit(run_single_query, item["query"], clean, a.timeout, str(child_cwd),
                                  a.model, a.plugin_dir, a.append_system_prompt)
                    fut[f] = item
            done = 0
            for f in as_completed(fut):
                item = fut[f]
                try:
                    outcome, detail = f.result()
                except Exception as e:
                    outcome, detail = "error", f"worker: {e}"
                runs.setdefault(item["query"], []).append((outcome, detail))
                done += 1
                print(f"\r  {done}/{len(fut)} runs", end="", file=sys.stderr, flush=True)
            print(file=sys.stderr)
    finally:
        if cfile is not None and cfile.exists():
            cfile.unlink()

    by_query = {i["query"]: i for i in eval_set}
    results, all_outcomes = [], Counter()
    for q, rs in runs.items():
        all_outcomes.update(o for o, _ in rs)
        valid = [o for o, _ in rs if o not in ("error", "timeout", "empty_stream")]
        trig = sum(1 for o in valid if o == "triggered")
        rate = trig / len(valid) if valid else None
        should = by_query[q]["should_trigger"]
        ok = None if rate is None else (rate >= a.trigger_threshold if should else rate < a.trigger_threshold)
        results.append({"query": q, "should_trigger": should, "trigger_rate": rate,
                        "triggers": trig, "valid_runs": len(valid), "runs": len(rs),
                        "outcomes": Counter(o for o, _ in rs), "details": rs, "pass": ok})

    bad = sum(all_outcomes[k] for k in ("error", "timeout", "empty_stream"))
    total_runs = sum(all_outcomes.values())
    err_rate = bad / total_runs if total_runs else 1.0
    scored = [r for r in results if r["pass"] is not None]
    pos = [r for r in scored if r["should_trigger"]]
    neg = [r for r in scored if not r["should_trigger"]]
    recall = sum(r["pass"] for r in pos) / len(pos) if pos else None
    spec = sum(r["pass"] for r in neg) / len(neg) if neg else None

    print(f"\n=== {label} · model={a.model or 'default'} · "
          f"{'plugin-dir' if a.plugin_dir else 'stub-skill'} mode ===")
    print(f"description ({len(desc)} chars): {desc[:110]}…")
    print("run outcomes: " + " · ".join(f"{k}={v}" for k, v in all_outcomes.most_common()))
    invalid = err_rate > a.max_error_rate or not scored or all_outcomes.get("triggered", 0) == 0
    if invalid:
        print(f"\n*** INVALID RUN — NOT A MEASUREMENT OF THE DESCRIPTION ***")
        if err_rate > a.max_error_rate:
            print(f"    {bad}/{total_runs} runs errored ({err_rate:.0%}) — above --max-error-rate {a.max_error_rate:.0%}")
        if all_outcomes.get("triggered", 0) == 0:
            print("    the skill never triggered in ANY run, including easy positives —")
            print("    check the model, the harness, and whether the child uses tools at all")
        for r in results[:3]:
            print(f"    e.g. {r['query'][:60]}… -> {r['details'][:2]}")
    else:
        # An arm may be positives-only or negatives-only; formatting None crashed the report
        # AFTER the runs were paid for and BEFORE --out was written, losing every detail.
        pct = lambda v: "n/a" if v is None else f"{v:.0%}"
        print(f"recall (positives)   : {pct(recall)}  ({sum(r['pass'] for r in pos)}/{len(pos)})")
        print(f"specificity (negs)   : {pct(spec)}  ({sum(r['pass'] for r in neg)}/{len(neg)})")
        for r in sorted(results, key=lambda r: (r["should_trigger"], r["trigger_rate"] or 0)):
            mark = "PASS" if r["pass"] else ("SKIP" if r["pass"] is None else "FAIL")
            rate = "n/a" if r["trigger_rate"] is None else f"{r['triggers']}/{r['valid_runs']}"
            print(f"  [{mark}] {rate} expect={r['should_trigger']!s:5} {r['query'][:64]}")

    out = {"label": label, "model": a.model, "description": desc, "invalid": invalid,
           "error_rate": err_rate, "outcomes": dict(all_outcomes),
           "recall": recall, "specificity": spec,
           "results": [{**r, "outcomes": dict(r["outcomes"])} for r in results]}
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print(f"wrote {a.out}")
    sys.exit(2 if invalid else 0)


if __name__ == "__main__":
    main()
