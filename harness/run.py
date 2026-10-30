#!/usr/bin/env python3
"""
harness/run.py — Minimal OpenCode headless evaluation harness.

Manages clean runs, logs manifest.json, events.jsonl, and done.json,
and executes external judges (done.ps1 or done.sh) isolated outside the repo.
Implements the contract defined in GEMINI.md, AGENTS.md, and 01-METRICS-SPEC.md v0.1.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Deterministic completion regex specified in AGENTS.md / METRICS-SPEC
CLAIM_RE = re.compile(r"^##\s*Done\b.*?\[x\]", re.S | re.M)

def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'))

def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def parse_args():
    parser = argparse.ArgumentParser(description="OpenCode Evaluation Harness")
    parser.add_argument("--task-id", required=True, help="Task ID (e.g. T01)")
    parser.add_argument("--config-id", required=True, help="Config ID (e.g. C0a)")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--block", type=int, default=1, help="Experiment block index")
    parser.add_argument("--repo-dir", required=True, help="Path to clean repo checkout")
    parser.add_argument("--prompt", required=True, help="Task prompt or path to prompt file")
    parser.add_argument("--judge", required=True, help="Path to external judge script (done.ps1 or done.sh)")
    parser.add_argument("--runs-dir", default="runs", help="Output directory for runs")
    parser.add_argument("--model", default="opencode/beam-free", help="Requested model identifier")
    parser.add_argument("--pricing-table", default="2026-09a", help="Pricing table ID")
    parser.add_argument("--pricing-window", default="off-peak", help="Pricing window")
    parser.add_argument("--timeout-s", type=int, default=300, help="Max run duration in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Simulate run without invoking opencode")
    return parser.parse_args()

def run_judge(judge_path, repo_dir, timeout_s=60):
    """
    Executes the external judge isolated outside repo_dir with repo_dir passed as argument or cwd.
    Supports .ps1 on Windows and .sh on Unix / PowerShell.
    """
    judge = Path(judge_path).resolve()
    if not judge.exists():
        return False, f"Judge script not found: {judge}"

    is_windows = platform.system().lower() == "windows"
    if judge.suffix == ".ps1" or (is_windows and judge.suffix != ".sh"):
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(judge), str(repo_dir)]
    else:
        cmd = ["sh", str(judge), str(repo_dir)]

    try:
        res = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=timeout_s
        )
        return (res.returncode == 0), res.stdout + ("\n" + res.stderr if res.stderr else "")
    except subprocess.TimeoutExpired:
        return False, "Judge execution timed out"
    except Exception as e:
        return False, f"Judge execution failed: {e}"

def _extract_token_int(data_dict, keys, default=0):
    for k in keys:
        if k in data_dict and data_dict[k] is not None:
            try:
                return int(data_dict[k])
            except (ValueError, TypeError):
                continue
    return default

def parse_opencode_json_output(stdout_text, run_id):
    """
    Parses OpenCode json/ndjson stream into events.jsonl turn and call records.
    Understands OpenCode's actual schema: tool_use, text, step_finish (with tokens).
    Returns (events, final_message, session_id).
    """
    events = []
    final_message = ""
    seq = 0
    reported_model = None
    session_id = None
    has_turn = False

    lines = [l.strip() for l in stdout_text.splitlines() if l.strip()]

    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            final_message += line + "\n"
            continue

        if isinstance(record.get("sessionID"), str):
            session_id = record["sessionID"]
        if isinstance(record.get("model"), str) and record["model"]:
            reported_model = record["model"]
        elif isinstance(record.get("model"), dict) and record["model"].get("id"):
            reported_model = f"{record['model'].get('providerID','')}/{record['model']['id']}"

        rec_type = record.get("type") or record.get("event") or ""
        part = record.get("part") if isinstance(record.get("part"), dict) else {}

        # Assistant text
        if rec_type in ("message", "assistant", "text"):
            msg_content = (part.get("text") if isinstance(part, dict) else None) or record.get("content") or record.get("text") or record.get("message") or ""
            if isinstance(msg_content, str):
                final_message += msg_content + "\n"

        # Tool call (OpenCode schema: type=tool_use)
        if rec_type in ("tool_use", "tool_call", "call"):
            tool_name = part.get("tool") or record.get("tool") or record.get("name") or "unknown"
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            args = state.get("input") if isinstance(state, dict) else None
            if args is None:
                args = record.get("args") or record.get("input") or {}
            args_canon = canonical_json(args)
            args_hash = hashlib.sha256(args_canon.encode('utf-8')).hexdigest()
            status = (state.get("status") if isinstance(state, dict) else None) or record.get("result") or "completed"
            result = "ok" if status in ("completed", "ok", "success") else "error"
            output = ""
            if isinstance(state, dict):
                oc = state.get("output")
                if isinstance(oc, str):
                    output = oc
                elif isinstance(state.get("content"), list) and state["content"]:
                    output = str(state["content"][0].get("text", ""))
                elif isinstance(state.get("content"), str):
                    output = state["content"]
            call_event = {
                "ev": "call",
                "t": int(time.time()),
                "run_id": run_id,
                "seq": seq,
                "call_idx": 0,
                "tool": tool_name,
                "args_canon_sha256": args_hash,
                "args_canon": args_canon,
                "result": result,
                "result_bytes": len(output),
                "truncated": None,
                "sig": f"{tool_name}_{args_hash}",
                "error_signature": None,
                "latency_ms": 0
            }
            events.append(call_event)
            seq += 1

        # Token usage (OpenCode: step_finish.part.tokens)
        tokens = None
        if rec_type == "step_finish" and isinstance(part.get("tokens"), dict):
            tokens = part["tokens"]
        elif "usage" in record and isinstance(record.get("usage"), dict):
            tokens = record["usage"]
        elif rec_type in ("usage", "turn") and isinstance(record, dict) and ("input" in record or "output" in record):
            tokens = record

        if tokens:
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            fresh = _extract_token_int(tokens, ["input", "in_fresh", "input_tokens", "prompt_tokens"], 0)
            cached = _extract_token_int(cache, ["read", "in_cached", "cached_tokens", "cache_read_input_tokens"], 0)
            if cached == 0:
                cached = _extract_token_int(tokens, ["in_cached", "cached_tokens", "cache_read_input_tokens"], 0)
            out = _extract_token_int(tokens, ["output", "out", "output_tokens", "completion_tokens"], 0)
            reasoning = _extract_token_int(tokens, ["reasoning"], 0)

            if "prompt_tokens" in tokens and "cached_tokens" in tokens:
                fresh = max(0, fresh - cached)

            turn_event = {
                "ev": "turn",
                "t": int(time.time()),
                "run_id": run_id,
                "seq": seq,
                "role": "root",
                "parent_seq": None,
                "model_reported": reported_model or "opencode-reported",
                "req": {
                    "n_messages": 1,
                    "n_tool_results": 0,
                    "largest_tool_result_bytes": 0,
                    "context_sha256": "",
                    "compaction": False
                },
                "usage": {
                    "in_fresh": fresh,
                    "in_cached": cached,
                    "out": out,
                    "reasoning": reasoning
                },
                "ote": 0.0,
                "tool_calls_emitted": 0,
                "latency_ms": 0
            }
            events.append(turn_event)
            seq += 1
            has_turn = True

    if not has_turn:
        events.append({
            "ev": "turn",
            "t": int(time.time()),
            "run_id": run_id,
            "seq": seq,
            "role": "root",
            "parent_seq": None,
            "model_reported": reported_model or "opencode-reported",
            "req": {"n_messages": 1, "n_tool_results": 0, "largest_tool_result_bytes": 0, "context_sha256": "", "compaction": False},
            "usage": {"in_fresh": 0, "in_cached": 0, "out": 0, "reasoning": 0},
            "ote": 0.0,
            "tool_calls_emitted": 0,
            "latency_ms": 0
        })

    return events, final_message, session_id

def execute_run(args):
    repo_dir = Path(args.repo_dir).resolve()
    if not repo_dir.exists():
        sys.exit(f"Error: repo directory does not exist: {repo_dir}")

    # Read prompt
    prompt_path = Path(args.prompt)
    if prompt_path.exists():
        prompt_text = prompt_path.read_text(encoding="utf-8")
    else:
        prompt_text = args.prompt

    # Git check for repo.dirty and commit hash
    git_commit = "unknown"
    git_dirty = False
    try:
        rev_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True)
        if rev_res.returncode == 0:
            git_commit = rev_res.stdout.strip()
        st_res = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo_dir), capture_output=True, text=True)
        if st_res.returncode == 0 and st_res.stdout.strip():
            git_dirty = True
    except Exception:
        pass

    # Build preliminary manifest (minus run_id)
    agents_file = repo_dir / "AGENTS.md"
    config_content = agents_file.read_text(encoding="utf-8") if agents_file.exists() else ""

    manifest_pre = {
        "schema": "te/0.1",
        "task_id": args.task_id,
        "config_id": args.config_id,
        "seed": args.seed,
        "block": args.block,
        "repo": {
            "commit": git_commit,
            "dirty": git_dirty,
            "snapshot_sha256": sha256_text(git_commit + str(repo_dir))
        },
        "harness": {
            "name": "opencode",
            "version": "2.2.2",
            "adapter": "opencode-harness"
        },
        "model": {
            "requested": args.model,
            "reported": args.model,
            "pinnable": True
        },
        "pricing": {
            "table_id": args.pricing_table,
            "window": args.pricing_window
        },
        "config_sha256": sha256_text(config_content) if config_content else sha256_text(""),
        "corpus_sha256": sha256_text(prompt_text),
        "capabilities": {
            "exact_tokens": True,
            "tool_args": True,
            "tool_results": True,
            "session_tree": True,
            "compaction_events": False
        },
        "attribution": "exact",
        "env": {
            "os": platform.platform(),
            "python": platform.python_version()
        },
        "wall_clock_ms": 0,
        "aborted": False
    }

    # Deterministic run_id
    run_id = hashlib.sha256(canonical_json(manifest_pre).encode('utf-8')).hexdigest()[:12]
    manifest = dict(manifest_pre)
    manifest["run_id"] = run_id

    run_dir = Path(args.runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    opencode_stdout = ""
    exit_code = 0

    if not args.dry_run:
        opencode_bin = shutil.which("opencode") or shutil.which("opencode.cmd")
        if not opencode_bin:
            sys.exit("Error: opencode executable not found in PATH")

        cmd = [
            opencode_bin,
            "run",
            "--format", "json",
            "--model", args.model,
            prompt_text
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=args.timeout_s
            )
            exit_code = proc.returncode
            opencode_stdout = proc.stdout
        except subprocess.TimeoutExpired:
            exit_code = 124
            manifest["aborted"] = True
    else:
        # Dry-run mock output for testing/smoke validation
        opencode_stdout = (
            '{"type": "usage", "in_fresh": 500, "in_cached": 1000, "out": 150}\n'
            '{"type": "message", "content": "## Done\\n- [x] Task objective satisfied\\n"}\n'
        )

    duration_ms = int((time.time() - start_time) * 1000)
    manifest["wall_clock_ms"] = duration_ms

    # Parse events and check completion claim
    events, final_message, session_id = parse_opencode_json_output(opencode_stdout, run_id)
    claims_done = bool(CLAIM_RE.search(final_message or ""))

    if session_id:
        manifest["session_id"] = session_id

    # Run external judge
    solved, judge_output = run_judge(args.judge, repo_dir)

    done_data = {
        "exit_code": exit_code,
        "solved": solved,
        "claims_done": claims_done,
        "overridden": False,
        "reason_code": None if solved else "judge_failed",
        "duration_ms": duration_ms,
        "stdout_sha256": sha256_text(opencode_stdout)
    }

    # Write run artifacts (write once, immutable)
    (run_dir / "stdout.txt").write_text(opencode_stdout, encoding="utf-8", errors="replace")
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (run_dir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (run_dir / "done.json").write_text(json.dumps(done_data, indent=2))

    print(f"Run completed: {run_id}")
    print(f"  Task: {args.task_id} | Config: {args.config_id} | Seed: {args.seed}")
    print(f"  Solved: {solved} | Claims Done: {claims_done} | Overclaim: {claims_done and not solved}")
    print(f"  Output logged to: {run_dir}")
    return run_id

def main():
    args = parse_args()
    execute_run(args)

if __name__ == "__main__":
    main()
