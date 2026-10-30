#!/usr/bin/env python3
"""
tools/audit_session.py — Audit token economics, call classification, and waste
on a live conversation transcript, OpenCode session, or completed harness benchmark run.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Ensure project root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import classification heuristics directly from te_analyze
from te_analyze import classify_calls, ote_of, load_prices, fmt, run_metrics

def audit_harness_run(run_dir_path, prices):
    run_dir = Path(run_dir_path)
    man_p = run_dir / "manifest.json"
    ev_p = run_dir / "events.jsonl"
    done_p = run_dir / "done.json"

    if not (man_p.exists() and ev_p.exists()):
        sys.exit(f"Invalid harness run directory (missing manifest.json or events.jsonl): {run_dir}")

    man = json.loads(man_p.read_text(encoding="utf-8"))
    ev = [json.loads(l) for l in ev_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = json.loads(done_p.read_text(encoding="utf-8")) if done_p.exists() else {}

    run = {"dir": run_dir, "manifest": man, "events": ev, "done": done}
    m = run_metrics(run, prices)

    print("\n" + "=" * 65)
    print(f"  TE-Agent Benchmark Run Audit: {m['run_id']}")
    print(f"  Task: {m['task_id']} | Config: {m['config_id']} | Seed: {m['seed']}")
    print("=" * 65)
    print(f"Status: {'SOLVED' if m['solved'] else 'FAILED'}")
    print(f"Claims Done: {m['claims_done']} | Overclaim: {m['overclaim']}")
    print(f"Total OTE: {fmt(m['ote'])} (Fresh: {fmt(m['in_fresh'])}, Cached: {fmt(m['in_cached'])}, Out: {fmt(m['out'])})")
    print(f"Tool Calls: {m['n_calls']} (Novel: {m['n_calls'] - m['n_retry'] - m['n_repeat']}, Retry: {m['n_retry']}, Repeat: {m['n_repeat']}, Denied: {m['n_denied']})")
    print(f"Loop Incidents (>=3 retries): {m['loop_incidents']}")
    print("=" * 65 + "\n")
    return m

def parse_transcript(transcript_path, prices, task_id="live_session", config_id="current"):
    path = Path(transcript_path)
    if not path.exists():
        sys.exit(f"Transcript not found: {path}")

    events = []
    seq = 0
    total_in_fresh = 0
    total_in_cached = 0
    total_out = 0
    claims_done = False
    claim_re = re.compile(r"^##\s*Done\b.*?\[x\]", re.S | re.M)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            step = json.loads(line)
            
            # Check content for completion claim
            content = step.get("content") or ""
            if claim_re.search(content):
                claims_done = True

            # Extract tool calls
            tool_calls = step.get("tool_calls") or []
            for idx, call in enumerate(tool_calls):
                tool_name = call.get("name") or "unknown"
                raw_args = json.dumps(call.get("args") or {}, sort_keys=True)
                args_canon = re.sub(r"\s+", " ", raw_args)
                import hashlib
                args_hash = hashlib.sha256(args_canon.encode('utf-8')).hexdigest()

                events.append({
                    "ev": "call",
                    "t": seq,
                    "seq": seq,
                    "call_idx": idx,
                    "role": "root",
                    "tool": tool_name,
                    "args_canon": args_canon,
                    "args_canon_sha256": args_hash,
                    "result": "ok" if step.get("status") != "ERROR" else "error"
                })
                seq += 1

            # Approximate turns based on message content without arbitrary padding constants
            if step.get("type") in ("PLANNER_RESPONSE", "USER_INPUT"):
                tok_len = len(content) // 4
                turn_event = {
                    "ev": "turn",
                    "t": seq,
                    "seq": seq,
                    "role": "root",
                    "usage": {
                        "in_fresh": tok_len if step.get("type") == "USER_INPUT" else 0,
                        "in_cached": 0,
                        "out": tok_len if step.get("type") == "PLANNER_RESPONSE" else 0
                    }
                }
                total_in_fresh += turn_event["usage"]["in_fresh"]
                total_in_cached += turn_event["usage"]["in_cached"]
                total_out += turn_event["usage"]["out"]
                events.append(turn_event)
                seq += 1

    calls, loops = classify_calls(events)

    n_calls = len(calls)
    n_retry = sum(1 for c in calls if c.get("cls") == "retry")
    n_repeat = sum(1 for c in calls if c.get("cls") == "repeat")
    n_denied = sum(1 for c in calls if c.get("cls") == "denied")
    n_novel = sum(1 for c in calls if c.get("cls") == "novel")

    return {
        "task_id": task_id,
        "config_id": config_id,
        "total_calls": n_calls,
        "novel_calls": n_novel,
        "retry_calls": n_retry,
        "repeat_calls": n_repeat,
        "denied_calls": n_denied,
        "loop_incidents": loops,
        "retry_rate": (n_retry / n_calls) if n_calls else 0.0,
        "repeat_rate": (n_repeat / n_calls) if n_calls else 0.0,
        "claims_done": claims_done,
        "est_in_fresh": total_in_fresh,
        "est_in_cached": total_in_cached,
        "est_out": total_out,
        "calls": calls
    }

def print_audit_report(data, prices):
    print("\n" + "=" * 65)
    print(f"  TE-Agent Conversation Audit: {data['task_id']} ({data['config_id']})")
    print("=" * 65)

    print(f"\n1. Tool Invocation Breakdown (Total: {data['total_calls']})")
    print(f"   - Novel (Productive):  {data['novel_calls']}")
    print(f"   - Repeat (Anti-Cache): {data['repeat_calls']}  ({data['repeat_rate']*100:.1f}%)")
    print(f"   - Retry (Error Loop):  {data['retry_calls']}   ({data['retry_rate']*100:.1f}%)")
    print(f"   - Denied (Permission): {data['denied_calls']}")
    print(f"   - Loop Incidents (>=3): {data['loop_incidents']}")

    print(f"\n2. Token-Economics (Estimated Usage)")
    print(f"   - Input (Fresh):    {fmt(data['est_in_fresh'])} tokens")
    print(f"   - Input (Cached):   {fmt(data['est_in_cached'])} tokens")
    print(f"   - Output:           {fmt(data['est_out'])} tokens")
    
    ote = round(prices["w_fresh"] * data["est_in_fresh"] + 
                prices["w_cache"] * data["est_in_cached"] + 
                data["est_out"], 1)
    print(f"   - Total OTE:        {fmt(ote)}")

    waste_rate = (data['repeat_calls'] + data['retry_calls']) / max(data['total_calls'], 1)
    wasted_ote = round(ote * waste_rate, 1)
    print(f"\n3. Waste & Efficiency")
    print(f"   - Overall Waste Rate:  {waste_rate * 100:.1f}%")
    print(f"   - Estimated Wasted OTE: {fmt(wasted_ote)}")

    print(f"\n4. Contract Compliance")
    print(f"   - External Judge Claims: {'Reported Done' if data['claims_done'] else 'Incomplete / No Claim'}")
    if data['loop_incidents'] > 0:
        print(f"   - [ALERT] 2-Strike / Loop Rule Violated ({data['loop_incidents']} loop incidents detected)")
    if data['repeat_calls'] > 0:
        print(f"   - [ALERT] Context-Reuse Rule Violated ({data['repeat_calls']} repeated reads)")

    print("=" * 65 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Audit token economics and call classifications of an agent session")
    parser.add_argument("--transcript", "-t", help="Path to transcript.jsonl log")
    parser.add_argument("--run", "-r", help="Path to completed harness run directory (runs/<run_id>)")
    parser.add_argument("--prices", default=str(PROJECT_ROOT / "prices.json"), help="Path to prices.json")
    args = parser.parse_args()

    prices = load_prices(args.prices)

    if args.run:
        audit_harness_run(args.run, prices)
        return

    # Find transcript
    t_path = args.transcript
    if not t_path:
        # Default to latest in brain
        brain_dir = Path.home() / ".gemini" / "antigravity-cli" / "brain"
        if brain_dir.exists():
            candidates = list(brain_dir.glob("*/.system_generated/logs/transcript.jsonl"))
            if candidates:
                candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                t_path = str(candidates[0])

    if not t_path:
        sys.exit("Error: No transcript found. Provide with --transcript <path> or --run <run_dir>")

    data = parse_transcript(t_path, prices)
    print_audit_report(data, prices)

if __name__ == "__main__":
    main()
