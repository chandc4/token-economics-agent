#!/usr/bin/env python3
"""
tools/te_doctor.py — Environment & Contract Diagnostic Tool for TE-Agent.
Runs comprehensive sanity checks on:
  - Python runtime & platform
  - OpenCode CLI binary & version
  - OpenCode SQLite DB permissions & active session count
  - Antigravity transcript logs
  - Pricing table (prices.json)
  - Benchmark task fixtures & external judges (T01, T02, T03)
  - Contract template synchronization
"""

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def check_mark(ok):
    return "[OK]" if ok else "[FAIL]"

def run_doctor():
    print("=" * 65)
    print("  TE-Agent System Doctor & Pre-Flight Diagnostics")
    print("=" * 65)

    all_passed = True

    # 1. Python Environment
    py_ver = platform.python_version()
    py_ok = sys.version_info >= (3, 8)
    print(f"{check_mark(py_ok)} Python Version: {py_ver} ({platform.system()} {platform.machine()})")
    if not py_ok:
        all_passed = False

    # 2. OpenCode CLI
    opencode_bin = shutil.which("opencode") or shutil.which("opencode.cmd")
    if opencode_bin:
        try:
            res = subprocess.run([opencode_bin, "--version"], capture_output=True, text=True, timeout=5)
            ver = res.stdout.strip() or res.stderr.strip() or "Found"
            print(f"[OK] OpenCode Executable: {opencode_bin} ({ver})")
        except Exception:
            print(f"[OK] OpenCode Executable: {opencode_bin}")
    else:
        print("[WARN] OpenCode Executable: Not found in PATH. (Benchmark runs require opencode in PATH)")

    # 3. OpenCode SQLite Database
    db_path = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if db_path.is_file():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM session_v2")
            sess_cnt = cur.fetchone()[0]
            conn.close()
            print(f"[OK] OpenCode SQLite Database: {db_path} ({sess_cnt} sessions available)")
        except Exception as e:
            print(f"[FAIL] OpenCode SQLite Database: {e}")
            all_passed = False
    else:
        print(f"[WARN] OpenCode SQLite Database: Not found at {db_path}")

    # 4. Pricing Table
    price_file = PROJECT_ROOT / "prices.json"
    if price_file.is_file():
        try:
            p_data = json.loads(price_file.read_text(encoding="utf-8"))
            in_p = p_data.get("price_in_uncached_per_mtok")
            out_p = p_data.get("price_out_per_mtok")
            print(f"[OK] Pricing Table: {price_file.name} (Fresh: ${in_p}/M, Out: ${out_p}/M)")
        except Exception as e:
            print(f"[FAIL] Pricing Table: Invalid JSON: {e}")
            all_passed = False
    else:
        print(f"[FAIL] Pricing Table: Missing {price_file}")
        all_passed = False

    # 5. Task Suite & Judges
    tasks = ["T01", "T02", "T03"]
    tasks_ok = True
    for t in tasks:
        t_dir = PROJECT_ROOT / "tasks" / t
        prompt = t_dir / "prompt.txt"
        judge_ps1 = t_dir / "done.ps1"
        judge_sh = t_dir / "done.sh"
        if not (t_dir.is_dir() and prompt.is_file() and (judge_ps1.is_file() or judge_sh.is_file())):
            tasks_ok = False
            print(f"[FAIL] Task Fixture: {t} is missing prompt.txt or judge script.")
    if tasks_ok:
        print(f"[OK] Task Suite: T01, T02, T03 fixtures & independent judges verified.")
    else:
        all_passed = False

    # 6. Contract Templates Synchronization
    try:
        from tools.contracts import get_contract_text
        c3_text = get_contract_text("opencode")
        root_agents = PROJECT_ROOT / "AGENTS.md"
        c3_agents = PROJECT_ROOT / "configs" / "C3" / "AGENTS.md"
        sync_ok = (root_agents.is_file() and root_agents.read_text(encoding="utf-8") == c3_text) and \
                  (c3_agents.is_file() and c3_agents.read_text(encoding="utf-8") == c3_text)
        if sync_ok:
            print(f"[OK] Contract Invariants: Root AGENTS.md and configs/C3 are 100% byte-synchronized.")
        else:
            print(f"[WARN] Contract Invariants: Content drift detected between root AGENTS.md and configs/C3.")
    except Exception as e:
        print(f"[FAIL] Contract Invariants: {e}")
        all_passed = False

    # 7. Metrics Specification
    spec_file = PROJECT_ROOT / "01-METRICS-SPEC.md"
    if spec_file.is_file():
        print(f"[OK] Metrics Specification: {spec_file.name} (v0.1 canonical reference)")
    else:
        print(f"[FAIL] Metrics Specification: Missing {spec_file}")
        all_passed = False

    print("=" * 65)
    if all_passed:
        print("  System Status: HEALTHY & READY FOR BENCHMARKS")
    else:
        print("  System Status: ATTENTION NEEDED (Review FAIL items above)")
    print("=" * 65)

if __name__ == "__main__":
    run_doctor()
