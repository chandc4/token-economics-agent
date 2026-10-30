#!/usr/bin/env python3
"""
tools/te_agent_app.py — TE-Agent Professional Command Center & Multi-Session Intelligence Cockpit.

Zero external dependencies (pure Python standard library + SQLite3).
Features:
  - Native OpenCode Session Sync: Reads directly from ~/.local/share/opencode/opencode.db.
  - Native Antigravity Session Sync: Reads from ~/.gemini/antigravity-cli/brain.
  - Professional Vertical Sidebar with Live Indicator, Project Hierarchy, and Search.
  - Interactive Call Inspection Modal (Click any call to view full input, output, and duration).
  - Clean UTF-8 encoding (no garbage characters).
  - Financial ticker ($ spent vs $ wasted).
"""

import argparse
import datetime
import hashlib
import http.server
import json
import os
import re
import socketserver
import sqlite3
import sys
import time
import urllib.parse
import webbrowser
from collections import Counter, defaultdict
from pathlib import Path

# Add project root to path for te_analyze
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PORT = 8844

try:
    from tools.contracts import get_contract_text, get_target_filename
except ImportError:
    from contracts import get_contract_text, get_target_filename

TEMPLATE_CONFIGS = {
    "opencode": get_contract_text("opencode"),
    "agy": get_contract_text("agy"),
    "cursor": get_contract_text("cursor"),
    "claude": get_contract_text("claude")
}

def clean_command_summary(args):
    """Convert raw messy JSON tool arguments into clear, humanized text."""
    if not isinstance(args, dict):
        return str(args)[:120]

    if "CommandLine" in args:
        cmd = str(args["CommandLine"]).strip()
        if (cmd.startswith('"') and cmd.endswith('"')) or (cmd.startswith("'") and cmd.endswith("'")):
            cmd = cmd[1:-1].strip()
        cmd = cmd.replace('\\"', '"').replace('\\\\', '\\')
        cmd = re.sub(r"^powershell\s+-ExecutionPolicy\s+Bypass\s+-Command\s+", "", cmd, flags=re.IGNORECASE)
        cmd = re.sub(r"^powershell\s+-ExecutionPolicy\s+Bypass\s+", "", cmd, flags=re.IGNORECASE)
        return cmd

    if "Path" in args or "path" in args:
        p = str(args.get("Path") or args.get("path"))
        start = args.get("StartLine")
        end = args.get("EndLine")
        if start and end:
            return f"{Path(p).name} [L{start}-L{end}]"
        return Path(p).name

    if "pattern" in args:
        return f"glob {args.get('pattern')} in {Path(args.get('path', '.')).name}"

    if "query" in args:
        return f"search '{args['query']}'"

    return json.dumps(args, sort_keys=True)[:100]

def get_opencode_sessions():
    """Extract real-time interactive OpenCode sessions directly from SQLite database."""
    opencode_sessions = []
    db_path = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if not db_path.is_file():
        return opencode_sessions

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        query = """
            SELECT id, title, directory, tokens_input, tokens_output, tokens_cache_read, time_created, time_updated
            FROM session_v2
            ORDER BY time_updated DESC
            LIMIT 15;
        """
        cur.execute(query)
        rows = cur.fetchall()
        now_ms = time.time() * 1000

        for r in rows:
            s_id, title, directory, in_tok, out_tok, cache_read, t_created, t_updated = r
            title = title or "Untitled Session"
            proj_name = Path(directory).name if directory else "OpenCode"
            is_active = (now_ms - t_updated) < 300_000  # active within 5 mins
            dt_str = datetime.datetime.fromtimestamp(t_updated / 1000).strftime("%b %d, %H:%M")

            opencode_sessions.append({
                "id": f"opencode::{s_id}",
                "name": title[:28] + ("..." if len(title) > 28 else ""),
                "full_id": s_id,
                "runtime": "OpenCode",
                "project_name": proj_name,
                "project_path": directory or "",
                "path": f"db://{s_id}",
                "mtime": t_updated / 1000,
                "time_str": dt_str,
                "is_active": is_active,
                "tokens_input": in_tok or 0,
                "tokens_output": out_tok or 0,
                "tokens_cache_read": cache_read or 0
            })
        conn.close()
    except Exception as e:
        print(f"[OpenCode DB Error]: {e}", file=sys.stderr)

    return opencode_sessions

def discover_all_sessions():
    """Discover sessions from Antigravity and OpenCode DB, grouped by project."""
    raw_sessions = []

    # 1. Antigravity Sessions
    agy_brain = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    if agy_brain.is_dir():
        for s_dir in agy_brain.iterdir():
            t_file = s_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if t_file.is_file():
                mtime = t_file.stat().st_mtime
                dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%b %d, %H:%M")
                is_active = (time.time() - mtime) < 300
                raw_sessions.append({
                    "id": f"agy::{s_dir.name}",
                    "name": f"AGY {s_dir.name[:8]}...",
                    "full_id": s_dir.name,
                    "runtime": "Antigravity",
                    "project_name": "opencode-setup" if "4da46631" in s_dir.name else "Antigravity Workspace",
                    "project_path": str(PROJECT_ROOT) if "4da46631" in s_dir.name else "",
                    "path": str(t_file),
                    "mtime": mtime,
                    "time_str": dt_str,
                    "is_active": is_active,
                    "size_kb": round(t_file.stat().st_size / 1024, 1)
                })

    # 2. OpenCode Interactive Sessions (from SQLite)
    opencode_sessions = get_opencode_sessions()
    raw_sessions.extend(opencode_sessions)

    # 3. Harness Benchmark Runs (from runs/ directory)
    runs_dir = PROJECT_ROOT / "runs"
    if runs_dir.is_dir():
        for r_dir in sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            events_file = r_dir / "events.jsonl"
            manifest_file = r_dir / "manifest.json"
            if events_file.is_file():
                mtime = events_file.stat().st_mtime
                dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%b %d, %H:%M")
                run_label = r_dir.name[:16]
                if manifest_file.is_file():
                    try:
                        man = json.loads(manifest_file.read_text(encoding="utf-8"))
                        t_id = man.get("task_id", "")
                        c_id = man.get("config_id", "")
                        s_id = man.get("seed", "")
                        run_label = f"{t_id} / {c_id} (s{s_id})"
                    except Exception:
                        pass
                raw_sessions.append({
                    "id": f"harness::{r_dir.name}",
                    "name": run_label,
                    "full_id": r_dir.name,
                    "runtime": "Harness",
                    "project_name": "Harness Benchmark Runs",
                    "project_path": str(PROJECT_ROOT),
                    "path": str(events_file),
                    "mtime": mtime,
                    "time_str": dt_str,
                    "is_active": False,
                    "size_kb": round(events_file.stat().st_size / 1024, 1)
                })

    # Sort descending by last modified
    raw_sessions.sort(key=lambda x: x["mtime"], reverse=True)

    # Group by project
    projects_map = defaultdict(list)
    for s in raw_sessions:
        projects_map[s["project_name"]].append(s)

    project_groups = []
    for p_name, s_list in projects_map.items():
        project_groups.append({
            "project_name": p_name,
            "project_path": s_list[0].get("project_path", ""),
            "session_count": len(s_list),
            "sessions": s_list
        })

    return {
        "all_sessions": raw_sessions,
        "projects": project_groups
    }

def parse_opencode_db_session(session_id):
    """Parse messages and tool calls for an OpenCode session directly from SQLite."""
    db_path = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if not db_path.is_file():
        return None

    timeline = []
    in_fresh = 0
    in_cached = 0
    out_tok = 0
    claims_done = False
    claim_re = re.compile(r"^##\s*Done\b.*?\[x\]", re.S | re.M)

    file_reads = Counter()
    file_edits = Counter()
    tool_counts = Counter()
    recent_reads = {}
    recent_results = {}   # sig -> (seq, result_label)
    consecutive_errors = {}  # sig -> consecutive failure count
    recent_errors = {}

    novel_count = 0
    retry_count = 0
    repeat_count = 0
    loop_incidents = 0
    untargeted_reads_total = 0
    seq = 0

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT tokens_input, tokens_output, tokens_cache_read FROM session_v2 WHERE id = ?;", (session_id,))
        meta = cur.fetchone()
        if meta:
            in_fresh = meta[0] or 0
            out_tok = meta[1] or 0
            in_cached = meta[2] or 0

        cur.execute("SELECT data FROM session_message WHERE session_id = ? ORDER BY time_created ASC;", (session_id,))
        rows = cur.fetchall()
        for r in rows:
            try:
                d = json.loads(r[0])
            except Exception:
                continue

            for c in d.get("content", []):
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    text = c.get("text", "")
                    if claim_re.search(text):
                        claims_done = True
                elif c.get("type") == "tool":
                    name = c.get("name", "tool")
                    tool_counts[name] += 1
                    state = c.get("state", {})
                    inp = state.get("input", {})
                    out_content = state.get("content", [])
                    out_text = ""
                    if isinstance(out_content, list) and out_content:
                        out_text = out_content[0].get("text", "")
                    elif isinstance(out_content, str):
                        out_text = out_content

                    classification = "novel"

                    untargeted_reads = 0

                    # Result status for retry detection
                    status = state.get("status", "")
                    result_ok = status in ("completed", "ok", "success", "done", "")
                    result_label = "ok" if result_ok else "error"

                    # Retry detection: same tool+args repeated after an error
                    call_sig = f"{name}::{json.dumps(inp, sort_keys=True)}"
                    if (call_sig in recent_results and recent_results[call_sig][1] == "error"
                            and (seq - recent_results[call_sig][0]) <= 4):
                        classification = "retry"
                        retry_count += 1

                    # Consecutive-error tracking for loop incidents
                    if not result_ok:
                        consecutive_errors[call_sig] = consecutive_errors.get(call_sig, 0) + 1
                        if consecutive_errors[call_sig] == 2:
                            loop_incidents += 1
                    else:
                        consecutive_errors[call_sig] = 0

                    recent_results[call_sig] = (seq, result_label)

                    # Track file reads
                    if name in ("read", "readFile", "glob", "grep"):
                        target = str(inp.get("path") or inp.get("filePath") or inp.get("pattern") or "")
                        if target:
                            basename = Path(target).name
                            file_reads[basename] += 1
                            if target in recent_reads and (seq - recent_reads[target]) <= 3 and classification != "retry":
                                classification = "repeat"
                                repeat_count += 1
                            recent_reads[target] = seq
                            # Check bounded range (only penalize large untargeted dumps)
                            if name in ("read", "readFile") and not (inp.get("offset") or inp.get("limit") or inp.get("StartLine")):
                                if len(out_text) > 8000:
                                    untargeted_reads += 1
                                    untargeted_reads_total += 1
                    elif name in ("write", "edit", "patch"):
                        target = str(inp.get("path") or inp.get("filePath") or "")
                        if target:
                            file_edits[Path(target).name] += 1

                    if classification == "novel":
                        novel_count += 1

                    clean_sum = clean_command_summary(inp)
                    timeline.append({
                        "seq": seq,
                        "tool": name,
                        "cls": classification,
                        "summary": clean_sum,
                        "raw_input": json.dumps(inp, indent=2),
                        "raw_output": out_text[:5000] if out_text else "No output payload"
                    })
                    seq += 1

        conn.close()
    except Exception as e:
        print(f"[OpenCode DB Parse Error]: {e}", file=sys.stderr)

    total_calls = len(timeline)

    # Prices table (load from prices.json for consistency with analyzer)
    price_in = 3.0
    price_cache = 0.3
    price_out = 15.0
    p_path = PROJECT_ROOT / "prices.json"
    if p_path.is_file():
        try:
            p_data = json.loads(p_path.read_text(encoding="utf-8"))
            price_in = p_data.get("price_in_uncached_per_mtok", price_in)
            price_cache = p_data.get("price_in_cached_per_mtok", price_cache)
            price_out = p_data.get("price_out_per_mtok", price_out)
        except Exception:
            pass
    out_price = price_out if price_out else 1.0
    w_fresh = price_in / out_price
    w_cache = price_cache / out_price
    ote_total = round((w_fresh * in_fresh) + (w_cache * in_cached) + out_tok, 1)

    cost_fresh_usd = (in_fresh / 1_000_000) * price_in
    cost_cached_usd = (in_cached / 1_000_000) * price_cache
    cost_out_usd = (out_tok / 1_000_000) * price_out
    total_cost_usd = round(cost_fresh_usd + cost_cached_usd + cost_out_usd, 4)

    waste_rate = round((repeat_count + retry_count) / max(total_calls, 1), 3)
    wasted_cost_usd = round(total_cost_usd * waste_rate, 4)

    # Discipline score per spec: -15 per repeat, -20 per loop, -10 per untargeted dump
    # Cap untargeted penalty to avoid over-penalizing when range metadata is absent
    untargeted_penalty = min(untargeted_reads_total, 5) * 10
    discipline_score = max(0, min(100, 100 - (repeat_count * 15) - (loop_incidents * 20) - untargeted_penalty))

    # Budget / governance alerts
    alerts = []
    if total_cost_usd > 1.0:
        alerts.append("Cost exceeds $1.00")
    if waste_rate > 0.2:
        alerts.append(f"High waste rate ({waste_rate*100:.1f}%)")
    if loop_incidents > 0:
        alerts.append(f"{loop_incidents} retry loop incident(s)")
    alert_text = "; ".join(alerts) if alerts else "OK"
    top_read_files = [{"file": f, "reads": c, "is_vampire": c >= 4 and file_edits[f] == 0} for f, c in file_reads.most_common(6)]
    top_tools = [{"tool": t, "count": c, "pct": round(c / max(total_calls, 1) * 100, 1)} for t, c in tool_counts.most_common(5)]

    narrative = f"OpenCode session executed {total_calls} tool actions. {discipline_score}/100 discipline score. "
    narrative += f"Processed {in_fresh:,} fresh tokens and {in_cached:,} cached tokens."

    return {
        "path": f"opencode.db::{session_id}",
        "total_calls": total_calls,
        "novel_calls": novel_count,
        "retry_calls": retry_count,
        "repeat_calls": repeat_count,
        "loop_incidents": loop_incidents,
        "waste_rate": waste_rate,
        "discipline_score": discipline_score,
        "claims_done": claims_done,
        "in_fresh": in_fresh,
        "in_cached": in_cached,
        "out_tok": out_tok,
        "ote_total": ote_total,
        "cost_total_usd": total_cost_usd,
        "cost_wasted_usd": wasted_cost_usd,
        "hotspots": top_read_files,
        "top_tools": top_tools,
        "narrative": narrative,
        "alert": alert_text,
        "timeline": timeline[-40:]
    }

def parse_session_intelligence(path_str):
    """Deep analysis of call streams: supports both Antigravity transcript and OpenCode DB."""
    if path_str.startswith("db://"):
        session_id = path_str.replace("db://", "")
        return parse_opencode_db_session(session_id)

    path = Path(path_str)
    if not path.is_file():
        return None

    prices = {"w_fresh": 0.2, "w_cache": 0.02, "price_in": 3.0, "price_cache": 0.3, "price_out": 15.0}
    p_path = PROJECT_ROOT / "prices.json"
    if p_path.is_file():
        try:
            p_data = json.loads(p_path.read_text(encoding="utf-8"))
            out = p_data.get("price_out_per_mtok", 15.0)
            prices["price_in"] = p_data.get("price_in_uncached_per_mtok", 3.0)
            prices["price_cache"] = p_data.get("price_in_cached_per_mtok", 0.3)
            prices["price_out"] = out
            prices["w_fresh"] = prices["price_in"] / out
            prices["w_cache"] = prices["price_cache"] / out
        except Exception:
            pass

    events = []
    seq = 0
    in_fresh = 0
    in_cached = 0
    out_tok = 0
    claims_done = False
    solved = None
    claim_re = re.compile(r"^##\s*Done\b.*?\[x\]", re.S | re.M)
    timeline = []

    file_reads = Counter()
    file_edits = Counter()
    tool_counts = Counter()

    recent_reads = {}
    recent_errors = {}

    novel_count = 0
    retry_count = 0
    repeat_count = 0
    loop_incidents = 0
    untargeted_reads = 0

    # Check for companion done.json (harness runs)
    done_file = path.parent / "done.json"
    if done_file.is_file():
        try:
            done_data = json.loads(done_file.read_text(encoding="utf-8"))
            claims_done = bool(done_data.get("claims_done", False))
            solved = bool(done_data.get("solved", False))
        except Exception:
            pass

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                step = json.loads(line)
            except Exception:
                continue

            # Case A: Harness events.jsonl
            if "ev" in step:
                ev_type = step.get("ev")
                if ev_type == "turn":
                    usage = step.get("usage", {})
                    in_fresh += usage.get("in_fresh", 0)
                    in_cached += usage.get("in_cached", 0)
                    out_tok += usage.get("out", 0)
                elif ev_type == "call":
                    name = step.get("tool", "tool")
                    tool_counts[name] += 1
                    args = step.get("args") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"raw": args}
                    result = step.get("result", "ok")
                    is_err = result in ("error", "timeout", "denied")

                    cls = step.get("cls")
                    if not cls:
                        cls = "novel"
                        if "read" in name.lower():
                            p_target = str(args.get("Path") or args.get("path") or "").lower()
                            if p_target:
                                if p_target in recent_reads and (seq - recent_reads[p_target]) <= 3:
                                    cls = "repeat"
                                recent_reads[p_target] = seq
                        if is_err and not cls == "repeat":
                            cls = "retry"

                    if cls == "repeat":
                        repeat_count += 1
                    elif cls == "retry":
                        retry_count += 1
                        loop_incidents += 1
                    else:
                        novel_count += 1

                    if "read" in name.lower():
                        p_target = str(args.get("Path") or args.get("path") or "").lower()
                        if p_target:
                            file_reads[Path(p_target).name] += 1
                        if not (args.get("StartLine") or args.get("EndLine")):
                            untargeted_reads += 1
                    elif "edit" in name.lower() or "write" in name.lower():
                        p_target = str(args.get("Path") or args.get("path") or "").lower()
                        if p_target:
                            file_edits[Path(p_target).name] += 1

                    clean_sum = clean_command_summary(args)
                    timeline.append({
                        "seq": seq,
                        "tool": name,
                        "cls": cls,
                        "summary": clean_sum,
                        "raw_input": json.dumps(args, indent=2),
                        "raw_output": f"Result: {result}"
                    })
                    seq += 1
                continue

            # Case B: Antigravity transcript.jsonl
            content = step.get("content") or ""
            if claim_re.search(content):
                claims_done = True

            tool_calls = step.get("tool_calls") or []
            status = step.get("status", "DONE")
            is_err = (status == "ERROR" or bool(step.get("error")))

            for call in tool_calls:
                func = call.get("function", {})
                name = func.get("name") or call.get("name") or "unknown"
                args = func.get("arguments") or call.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"raw": args}

                tool_counts[name] += 1
                raw_args = json.dumps(args, sort_keys=True)
                args_canon = re.sub(r"\s+", " ", raw_args)
                args_hash = hashlib.sha256(args_canon.encode('utf-8')).hexdigest()
                sig = f"{name}::{args_hash[:16]}"

                classification = "novel"

                if "read" in name.lower() or name in ("read_file", "view_file"):
                    p_target = str(args.get("Path") or args.get("path") or "").lower()
                    if p_target:
                        basename = Path(p_target).name
                        file_reads[basename] += 1
                        if p_target in recent_reads and (seq - recent_reads[p_target]) <= 3:
                            classification = "repeat"
                            repeat_count += 1
                        recent_reads[p_target] = seq
                    if not (args.get("StartLine") or args.get("EndLine")):
                        untargeted_reads += 1
                elif "edit" in name.lower() or "write" in name.lower():
                    p_target = str(args.get("Path") or args.get("path") or "").lower()
                    if p_target:
                        file_edits[Path(p_target).name] += 1

                if is_err:
                    if sig in recent_errors and (seq - recent_errors[sig]) <= 2:
                        classification = "retry"
                        retry_count += 1
                        loop_incidents += 1
                    recent_errors[sig] = seq

                if classification == "novel":
                    novel_count += 1

                clean_sum = clean_command_summary(args)
                timeline.append({
                    "seq": seq,
                    "tool": name,
                    "cls": classification,
                    "summary": clean_sum,
                    "raw_input": json.dumps(args, indent=2),
                    "raw_output": content[:5000] if content else "Executed"
                })
                seq += 1

            tok_len = len(content) // 4
            if step.get("type") == "USER_INPUT":
                in_fresh += tok_len
            else:
                out_tok += tok_len

    total_calls = len(timeline)
    ote_total = round((prices["w_fresh"] * in_fresh) + (prices["w_cache"] * in_cached) + out_tok, 1)

    cost_fresh_usd = (in_fresh / 1_000_000) * prices["price_in"]
    cost_cached_usd = (in_cached / 1_000_000) * prices["price_cache"]
    cost_out_usd = (out_tok / 1_000_000) * prices["price_out"]
    total_cost_usd = round(cost_fresh_usd + cost_cached_usd + cost_out_usd, 4)

    waste_rate = round((repeat_count + retry_count) / max(total_calls, 1), 3)
    wasted_cost_usd = round(total_cost_usd * waste_rate, 4)

    # Standardized discipline score (§5 01-METRICS-SPEC.md)
    discipline_score = max(0, min(100, 100 - (repeat_count * 15) - (loop_incidents * 20) - (untargeted_reads * 10)))
    top_read_files = [{"file": f, "reads": c, "is_vampire": c >= 4 and file_edits[f] == 0} for f, c in file_reads.most_common(6)]
    top_tools = [{"tool": t, "count": c, "pct": round(c / max(total_calls, 1) * 100, 1)} for t, c in tool_counts.most_common(5)]

    narrative = f"The agent executed {total_calls} calls with a {discipline_score}/100 discipline score. "
    if waste_rate <= 0.05:
        narrative += f"Clean token economy observed ({round((1 - waste_rate) * 100, 1)}% productive calls). "
    else:
        narrative += f"Waste rate reached {round(waste_rate * 100, 1)}% due to repeat reads or retries. "
    if loop_incidents == 0:
        narrative += "Zero retry loops were triggered."
    else:
        narrative += f"Encountered {loop_incidents} loop incidents."
    if claims_done and solved is False:
        narrative += " [OVERCLAIM ALERT: Completion claimed but external judge failed!]"
    elif claims_done and solved is True:
        narrative += " [VERIFIED: External judge passed completion criteria cleanly.]"

    return {
        "path": str(path),
        "total_calls": total_calls,
        "novel_calls": novel_count,
        "retry_calls": retry_count,
        "repeat_calls": repeat_count,
        "loop_incidents": loop_incidents,
        "waste_rate": waste_rate,
        "discipline_score": discipline_score,
        "claims_done": claims_done,
        "solved": solved,
        "in_fresh": in_fresh,
        "in_cached": in_cached,
        "out_tok": out_tok,
        "ote_total": ote_total,
        "cost_total_usd": total_cost_usd,
        "cost_wasted_usd": wasted_cost_usd,
        "hotspots": top_read_files,
        "top_tools": top_tools,
        "narrative": narrative,
        "timeline": timeline[-40:]
    }

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TE-Agent Enterprise Cockpit</title>
  <style>
    :root {
      --bg: #0b0f19;
      --sidebar-bg: #111827;
      --card-bg: #131c2e;
      --card-border: #1f293d;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.2);
      --accent-hover: #0284c7;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --text: #f9fafb;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif; }
    body { background-color: var(--bg); color: var(--text); font-size: 13px; height: 100vh; overflow: hidden; display: flex; }

    /* Left Sidebar */
    .sidebar { width: 320px; background: var(--sidebar-bg); border-right: 1px solid var(--card-border); display: flex; flex-direction: column; flex-shrink: 0; }
    .sidebar-header { padding: 16px; border-bottom: 1px solid var(--card-border); }
    .brand { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
    .brand h2 { font-size: 16px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
    .brand-badge { background: #1e293b; color: var(--accent); padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; border: 1px solid var(--accent); }
    .search-box { width: 100%; padding: 8px 12px; background: #0b0f19; border: 1px solid var(--card-border); border-radius: 6px; color: #fff; font-size: 12px; }

    /* Vertical Sessions List */
    .session-list-container { flex: 1; overflow-y: auto; padding: 12px; }
    .proj-group-title { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin: 12px 6px 6px 6px; }
    .session-card { background: #182234; border: 1px solid #233149; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; cursor: pointer; transition: all 0.15s; }
    .session-card:hover { border-color: var(--accent); }
    .session-card.active { background: #1e2e4a; border-color: var(--accent); box-shadow: 0 0 10px var(--accent-glow); }
    .session-card-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
    .runtime-badge { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
    .runtime-badge.opencode { background: #0284c7; color: #fff; }
    .runtime-badge.agy { background: #7c3aed; color: #fff; }
    .session-card-title { font-weight: 600; color: #fff; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .session-card-time { font-size: 10px; color: var(--text-muted); }
    .active-dot { width: 6px; height: 6px; background: var(--success); border-radius: 50%; box-shadow: 0 0 6px var(--success); }

    /* Main Content Area */
    .main-content { flex: 1; display: flex; flex-direction: column; overflow-y: auto; padding: 20px; }

    /* Top Navigation Tabs */
    .top-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; border-bottom: 1px solid var(--card-border); padding-bottom: 14px; }
    .view-tabs { display: flex; gap: 8px; }
    .tab-btn { background: #111827; border: 1px solid var(--card-border); color: var(--text-muted); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; }
    .tab-btn:hover { color: #fff; border-color: var(--accent); }
    .tab-btn.active { background: var(--accent); color: #000; border-color: var(--accent); }

    /* 4 Financial & Operational Cards */
    .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
    .stat-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 14px; }
    .stat-label { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; }
    .stat-val { font-size: 22px; font-weight: 700; color: #fff; }
    .stat-sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
    .val-good { color: var(--success); }
    .val-warn { color: var(--warning); }
    .val-danger { color: var(--danger); }

    /* View Panes */
    .view-pane { display: none; }
    .view-pane.active { display: block; }

    /* Interactive Timeline Table */
    .timeline-container { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 16px; }
    .timeline-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .timeline-table { width: 100%; border-collapse: collapse; font-family: monospace; font-size: 12px; }
    .timeline-table th { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--card-border); color: var(--text-muted); font-size: 11px; text-transform: uppercase; }
    .timeline-row { cursor: pointer; transition: background 0.15s; }
    .timeline-row:hover { background: #1a263d; }
    .timeline-row td { padding: 9px 12px; border-bottom: 1px solid #1a2436; }
    .chip { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
    .chip.novel { background: rgba(16, 185, 129, 0.15); color: var(--success); }
    .chip.retry { background: rgba(239, 68, 68, 0.15); color: var(--danger); }
    .chip.repeat { background: rgba(245, 158, 11, 0.15); color: var(--warning); }

    /* Modal for Inspection */
    .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); backdrop-filter: blur(3px); z-index: 1000; justify-content: center; align-items: center; }
    .modal-overlay.active { display: flex; }
    .modal-card { width: 750px; max-height: 85vh; background: #111827; border: 1px solid var(--accent); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 0 24px rgba(56, 189, 248, 0.2); }
    .modal-header { padding: 14px 18px; border-bottom: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center; background: #0f172a; }
    .modal-body { padding: 18px; overflow-y: auto; flex: 1; font-family: monospace; font-size: 12px; }
    .modal-section { margin-bottom: 14px; }
    .modal-section-title { font-weight: 700; color: var(--accent); margin-bottom: 6px; font-size: 11px; text-transform: uppercase; }
    .code-box { background: #070a11; border: 1px solid #1e293b; border-radius: 6px; padding: 10px; color: #cbd5e1; max-height: 240px; overflow-y: auto; white-space: pre-wrap; }

    /* Studio & Intelligence Tabs */
    .studio-box { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 20px; }
    .studio-editor { width: 100%; height: 420px; background: #080d16; border: 1px solid var(--card-border); border-radius: 6px; color: #e2e8f0; font-family: monospace; font-size: 12px; padding: 12px; margin-top: 10px; }
  </style>
</head>
<body>

  <!-- Left Vertical Sidebar -->
  <div class="sidebar">
    <div class="sidebar-header">
      <div class="brand">
        <h2>TE-Agent</h2>
        <span class="brand-badge">PRO COCKPIT</span>
      </div>
      <input type="text" class="search-box" id="searchSessions" placeholder="Search sessions..." oninput="filterSessions()">
    </div>
    <div class="session-list-container" id="sessionList">
      <div style="padding: 12px; color:var(--text-muted);">Syncing OpenCode & AGY...</div>
    </div>
  </div>

  <!-- Main Content Area -->
  <div class="main-content">
    <div class="top-bar">
      <div class="view-tabs">
        <button class="tab-btn active" onclick="switchView('stream')">Live Call Stream</button>
        <button class="tab-btn" onclick="switchView('intel')">Stream Intelligence</button>
        <button class="tab-btn" onclick="switchView('studio')">Contract Studio</button>
      </div>
      <div style="font-size:11px; color:var(--text-muted); display:flex; align-items:center; gap:6px;">
        <span class="active-dot"></span> Auto-syncing every 4s
      </div>
    </div>

    <!-- 4 Financial & Operational Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Total Token Burn (OTE)</div>
        <div class="stat-val" id="oteVal">--</div>
        <div class="stat-sub" id="oteSub">Fresh: -- | Cached: --</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Financial Cost ($)</div>
        <div class="stat-val" id="costVal">$0.000</div>
        <div class="stat-sub val-warn" id="wastedCostSub">Wasted: $0.000</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Waste Rate</div>
        <div class="stat-val" id="wasteVal">0.0%</div>
        <div class="stat-sub" id="wasteSub">Repeat: 0 | Retry: 0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Discipline Score</div>
        <div class="stat-val" id="scoreVal">--/100</div>
        <div class="stat-sub" id="claimSub">Status: Pending</div>
      </div>
    </div>

    <!-- VIEW 1: LIVE CALL STREAM -->
    <div class="view-pane active" id="pane-stream">
      <div class="timeline-container">
        <div class="timeline-header">
          <h3 style="font-size:14px; font-weight:600;">Tool Invocations (Click row to inspect)</h3>
          <span style="font-size:12px; color:var(--text-muted);" id="callCountLabel">0 calls</span>
        </div>
        <table class="timeline-table">
          <thead>
            <tr>
              <th style="width: 50px;">#</th>
              <th style="width: 80px;">Class</th>
              <th style="width: 130px;">Tool</th>
              <th>Operation / Summary</th>
            </tr>
          </thead>
          <tbody id="timelineRows">
            <tr><td colspan="4">Select a session from the left sidebar...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- VIEW 2: STREAM INTELLIGENCE -->
    <div class="view-pane" id="pane-intel">
      <div class="studio-box" style="margin-bottom: 16px;">
        <h3 style="font-size:14px; margin-bottom:8px; color:var(--accent);">Automated Narrative Analysis</h3>
        <p id="intelNarrative" style="line-height:1.6; color:#cbd5e1;">Generating intelligence...</p>
      </div>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
        <div class="studio-box">
          <h3 style="font-size:13px; margin-bottom:8px;">File Access Hotspots (Context Vampires)</h3>
          <div id="hotspotBox">Loading...</div>
        </div>
        <div class="studio-box">
          <h3 style="font-size:13px; margin-bottom:8px;">Tool Invocation Breakdown</h3>
          <div id="toolBreakdownBox">Loading...</div>
        </div>
      </div>
    </div>

    <!-- VIEW 3: CONTRACT STUDIO -->
    <div class="view-pane" id="pane-studio">
      <div class="studio-box">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <div>
            <h3 style="font-size:15px;">Invariant Contract Studio</h3>
            <p style="font-size:12px; color:var(--text-muted);">Scaffold lean, anti-loop rules directly into your workspace.</p>
          </div>
          <div style="display:flex; gap:10px;">
            <select id="studioPlatform" onchange="loadStudioTemplate()" style="padding:6px 12px; background:#1e293b; color:#fff; border:1px solid #334155; border-radius:6px;">
              <option value="opencode">OpenCode (AGENTS.md)</option>
              <option value="agy">Antigravity (~/.gemini)</option>
              <option value="cursor">Cursor (.cursorrules)</option>
              <option value="claude">Claude Code (CLAUDE.md)</option>
            </select>
            <button onclick="applyStudioContract()" style="padding:6px 14px; background:var(--accent); color:#000; border:none; border-radius:6px; font-weight:700; cursor:pointer;">
              Deploy Contract
            </button>
          </div>
        </div>
        <div id="studioStatus" style="font-size:12px; margin-bottom:6px; color:var(--success);"></div>
        <textarea class="studio-editor" id="studioEditor"></textarea>
      </div>
    </div>
  </div>

  <!-- Call Inspection Modal -->
  <div class="modal-overlay" id="callModal" onclick="closeModal(event)">
    <div class="modal-card" onclick="event.stopPropagation()">
      <div class="modal-header">
        <h3 id="modalTitle" style="font-size:14px; color:#fff;">Tool Call Inspection</h3>
        <button onclick="closeModal()" style="background:transparent; border:none; color:#fff; font-size:18px; cursor:pointer;">&times;</button>
      </div>
      <div class="modal-body">
        <div class="modal-section">
          <div class="modal-section-title">Input Parameters</div>
          <pre class="code-box" id="modalInput"></pre>
        </div>
        <div class="modal-section">
          <div class="modal-section-title">Execution Result / Output Payload</div>
          <pre class="code-box" id="modalOutput"></pre>
        </div>
      </div>
    </div>
  </div>

  <script>
    let sessionData = { all_sessions: [], projects: [] };
    let activeSessionId = null;
    let currentTimeline = [];

    function switchView(viewName) {
      document.querySelectorAll('.view-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      document.getElementById('pane-' + viewName).classList.add('active');
      event.target.classList.add('active');
    }

    async function loadSessions() {
      try {
        const res = await fetch('/api/sessions');
        sessionData = await res.json();
        renderSidebar();
        if (!activeSessionId && sessionData.all_sessions.length > 0) {
          selectSession(sessionData.all_sessions[0].id);
        }
      } catch (e) {
        console.error("Failed to load sessions", e);
      }
    }

    function renderSidebar() {
      const container = document.getElementById('sessionList');
      container.innerHTML = '';

      sessionData.projects.forEach(proj => {
        const groupTitle = document.createElement('div');
        groupTitle.className = 'proj-group-title';
        groupTitle.innerText = `${proj.project_name} (${proj.session_count})`;
        container.appendChild(groupTitle);

        proj.sessions.forEach(s => {
          const card = document.createElement('div');
          card.className = 'session-card' + (s.id === activeSessionId ? ' active' : '');
          const runtimeClass = s.runtime.toLowerCase();
          card.innerHTML = `
            <div class="session-card-top">
              <span class="runtime-badge ${runtimeClass}">${s.runtime}</span>
              <div style="display:flex; align-items:center; gap:6px;">
                ${s.is_active ? '<div class="active-dot"></div>' : ''}
                <span class="session-card-time">${s.time_str}</span>
              </div>
            </div>
            <div class="session-card-title">${s.name}</div>
          `;
          card.onclick = () => selectSession(s.id);
          container.appendChild(card);
        });
      });
    }

    function filterSessions() {
      const q = document.getElementById('searchSessions').value.toLowerCase();
      document.querySelectorAll('.session-card').forEach(card => {
        const text = card.innerText.toLowerCase();
        card.style.display = text.includes(q) ? 'block' : 'none';
      });
    }

    async function selectSession(sessionId) {
      activeSessionId = sessionId;
      renderSidebar();
      try {
        const res = await fetch('/api/audit?session_id=' + encodeURIComponent(sessionId));
        const data = await res.json();
        renderAudit(data);
      } catch (e) {
        console.error("Failed to fetch session audit", e);
      }
    }

    function renderAudit(data) {
      document.getElementById('oteVal').innerText = Number(data.ote_total).toLocaleString();
      document.getElementById('oteSub').innerText = `Fresh: ${Number(data.in_fresh).toLocaleString()} | Cached: ${Number(data.in_cached).toLocaleString()}`;

      document.getElementById('costVal').innerText = '$' + Number(data.cost_total_usd).toFixed(4);
      document.getElementById('wastedCostSub').innerText = `Wasted: $${Number(data.cost_wasted_usd).toFixed(4)} (${(data.waste_rate * 100).toFixed(1)}%)`;

      const wrEl = document.getElementById('wasteVal');
      wrEl.innerText = (data.waste_rate * 100).toFixed(1) + '%';
      wrEl.className = 'stat-val ' + (data.waste_rate > 0.15 ? 'val-danger' : (data.waste_rate > 0.05 ? 'val-warn' : 'val-good'));
      document.getElementById('wasteSub').innerText = `Repeat: ${data.repeat_calls} | Retry: ${data.retry_calls}`;

      document.getElementById('scoreVal').innerText = `${data.discipline_score}/100`;
      document.getElementById('claimSub').innerText = `Status: ${data.claims_done ? 'Claim Verified' : 'In Progress'}`;

      // Timeline
      currentTimeline = data.timeline || [];
      document.getElementById('callCountLabel').innerText = `${data.total_calls} calls recorded`;
      const tbody = document.getElementById('timelineRows');
      tbody.innerHTML = '';

      if (currentTimeline.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="padding:16px;">No tool calls recorded in this session.</td></tr>';
      } else {
        currentTimeline.forEach((call, idx) => {
          const tr = document.createElement('tr');
          tr.className = 'timeline-row';
          tr.onclick = () => openCallModal(idx);
          tr.innerHTML = `
            <td style="color:var(--text-muted);">${call.seq}</td>
            <td><span class="chip ${call.cls}">${call.cls}</span></td>
            <td style="font-weight:600; color:#fff;">${call.tool}</td>
            <td style="color:#cbd5e1; max-width:550px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${call.summary}</td>
          `;
          tbody.appendChild(tr);
        });
      }

      // Intelligence Tab
      document.getElementById('intelNarrative').innerText = (data.alert && data.alert !== "OK" ? "ALERT: " + data.alert + " | " : "") + (data.narrative || "No narrative generated.");

      // Hotspots
      const hsBox = document.getElementById('hotspotBox');
      hsBox.innerHTML = '';
      if (!data.hotspots || data.hotspots.length === 0) {
        hsBox.innerHTML = '<p style="color:var(--text-muted);">No repeat file reads detected.</p>';
      } else {
        data.hotspots.forEach(h => {
          const d = document.createElement('div');
          d.style = 'display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1e293b;';
          d.innerHTML = `<span>${h.file}</span><b style="color:${h.is_vampire ? 'var(--danger)' : 'var(--text)'};">${h.reads} reads</b>`;
          hsBox.appendChild(d);
        });
      }

      // Breakdown
      const tbBox = document.getElementById('toolBreakdownBox');
      tbBox.innerHTML = '';
      if (data.top_tools) {
        data.top_tools.forEach(t => {
          const d = document.createElement('div');
          d.style = 'display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid #1e293b;';
          d.innerHTML = `<span>${t.tool}</span><b>${t.count} (${t.pct}%)</b>`;
          tbBox.appendChild(d);
        });
      }
    }

    function openCallModal(idx) {
      const item = currentTimeline[idx];
      if (!item) return;
      document.getElementById('modalTitle').innerText = `Call #${item.seq}: ${item.tool} [${item.cls.toUpperCase()}]`;
      document.getElementById('modalInput').innerText = item.raw_input || item.summary;
      document.getElementById('modalOutput').innerText = item.raw_output || "Executed cleanly.";
      document.getElementById('callModal').classList.add('active');
    }

    function closeModal() {
      document.getElementById('callModal').classList.remove('active');
    }

    async function loadStudioTemplate() {
      const p = document.getElementById('studioPlatform').value;
      const res = await fetch('/api/template?platform=' + p);
      const data = await res.json();
      document.getElementById('studioEditor').value = data.template;
    }

    async function applyStudioContract() {
      const p = document.getElementById('studioPlatform').value;
      const customContent = document.getElementById('studioEditor').value;
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform: p, content: customContent })
      });
      const data = await res.json();
      const statusEl = document.getElementById('studioStatus');
      if (data.success) {
        statusEl.innerText = `Deploy successful: created ${data.filename} (${data.bytes} bytes)`;
      } else {
        statusEl.innerText = `Error: ${data.error}`;
      }
    }

    setInterval(() => {
      if (activeSessionId) {
        selectSession(activeSessionId);
      }
    }, 4000);

    loadSessions();
    loadStudioTemplate();
  </script>
</body>
</html>
"""

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))

        elif parsed.path == "/api/sessions":
            sessions = discover_all_sessions()
            self.send_json(sessions)

        elif parsed.path == "/api/audit":
            session_id = qs.get("session_id", [None])[0]
            sessions = discover_all_sessions()["all_sessions"]
            target_path = None
            if session_id:
                for s in sessions:
                    if s["id"] == session_id:
                        target_path = s["path"]
                        break
            if not target_path and sessions:
                target_path = sessions[0]["path"]

            if not target_path:
                self.send_json({"error": "No session found"})
                return

            data = parse_session_intelligence(target_path)
            self.send_json(data or {"error": "Failed to parse session"})

        elif parsed.path == "/api/template":
            platform = qs.get("platform", ["opencode"])[0]
            template = TEMPLATE_CONFIGS.get(platform, TEMPLATE_CONFIGS["opencode"])
            self.send_json({"platform": platform, "template": template})

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/generate":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                payload = json.loads(body)
                platform = payload.get("platform", "opencode")
                content = payload.get("content") or TEMPLATE_CONFIGS.get(platform, TEMPLATE_CONFIGS["opencode"])
                filename = "AGENTS.md"
                if platform == "cursor":
                    filename = ".cursorrules"
                elif platform == "claude":
                    filename = "CLAUDE.md"
                elif platform == "agy":
                    filename = get_target_filename(platform)

                workspace = payload.get("workspace_path") or str(PROJECT_ROOT)
                target_dir = Path(workspace)
                if not target_dir.is_dir():
                    target_dir = PROJECT_ROOT
                out_path = target_dir / filename
                out_path.write_text(content, encoding="utf-8")
                self.send_json({"success": True, "filename": filename, "path": str(out_path), "bytes": len(content.encode('utf-8'))})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        pass

class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def run_server(open_browser=True):
    with ThreadingServer(("127.0.0.1", PORT), DashboardHandler) as httpd:
        url = f"http://localhost:{PORT}"
        print(f"\n" + "=" * 65)
        print(f"  TE-Agent Enterprise Cockpit running at: {url}")
        print(f"  Multi-Runtime Sync Active: OpenCode DB, Antigravity, & Harness Runs")
        print("=" * 65 + "\n")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard stopped.")

def main():
    parser = argparse.ArgumentParser(description="TE-Agent Pro Command Center")
    subparsers = parser.add_subparsers(dest="command")

    ui_p = subparsers.add_parser("ui", help="Launch web dashboard")
    ui_p.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    init_p = subparsers.add_parser("init", help="Generate contract config")
    init_p.add_argument("--platform", default="opencode", choices=["opencode", "agy", "cursor", "claude"])
    init_p.add_argument("--output", "-o", default="", help="Custom output file path")
    init_p.add_argument("--force", "-f", action="store_true", help="Overwrite existing configuration")

    audit_p = subparsers.add_parser("audit", help="Audit token metrics on current session")
    audit_p.add_argument("--path", "-p", default="", help="Path to transcript.jsonl or events.jsonl or session ID")

    args = parser.parse_args()

    if args.command == "ui" or not args.command:
        run_server(open_browser=not getattr(args, "no_browser", False))
    elif args.command == "init":
        template = get_contract_text(args.platform)
        fname = args.output if args.output else get_target_filename(args.platform)
        out_path = Path(fname).resolve()
        if out_path.exists() and not getattr(args, "force", False):
            sys.exit(f"File {out_path} already exists. Use --force to overwrite.")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(template, encoding="utf-8")
        print(f"Created {out_path.name} at {out_path} ({len(template)} bytes)")
    elif args.command == "audit":
        target = args.path
        if not target:
            sessions = discover_all_sessions()["all_sessions"]
            if sessions:
                target = sessions[0]["path"]
        if target:
            data = parse_session_intelligence(target)
            if data:
                print(f"Auditing target: {target}")
                print(f"Total Calls: {data['total_calls']} (Novel: {data['novel_calls']}, Repeat: {data['repeat_calls']}, Retry: {data['retry_calls']})")
                print(f"Total OTE: {data['ote_total']} | Total Cost: ${data['cost_total_usd']} (Wasted: ${data['cost_wasted_usd']})")
                print(f"Discipline Score: {data['discipline_score']}/100")
                print(f"Claims Done: {data['claims_done']} | Solved: {data.get('solved')}")
                print(f"Narrative: {data['narrative']}")
            else:
                print(f"Could not parse data for: {target}")

if __name__ == "__main__":
    main()
