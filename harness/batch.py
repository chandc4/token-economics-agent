#!/usr/bin/env python3
"""
harness/batch.py — Interleaved Batch Evaluation Scheduler.

Orchestrates multi-task, multi-seed, multi-config benchmark runs.
Enforces the runbook defined in 01-METRICS-SPEC.md v0.1:
  - Interleaving by (task, seed): e.g. T01/S1/C0a, T01/S1/C0b, T01/S2/C0a, T01/S2/C0b.
  - Creates isolated clean workspace checkouts per run from fixture templates.
  - Executes harness/run.py to capture manifest.json, events.jsonl, and done.json.
  - Leaves the repository in a clean state upon completion.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def parse_args():
    parser = argparse.ArgumentParser(description="Interleaved Batch Evaluation Scheduler")
    parser.add_argument("--configs", nargs="+", required=True, help="List of config IDs (e.g. C0a C0b)")
    parser.add_argument("--tasks", nargs="+", required=True, help="List of task IDs (e.g. T01 T02 T03)")
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3], help="Random seeds (e.g. 1 2 3)")
    parser.add_argument("--block", type=int, default=1, help="Block identifier")
    parser.add_argument("--tasks-dir", default=str(PROJECT_ROOT / "tasks"), help="Directory containing task definitions")
    parser.add_argument("--configs-dir", default=str(PROJECT_ROOT / "configs"), help="Directory containing config templates")
    parser.add_argument("--runs-dir", default=str(PROJECT_ROOT / "runs"), help="Directory where run results are stored")
    parser.add_argument("--model", default="opencode/beam-free", help="Pinned model name")
    parser.add_argument("--interleave", action="store_true", default=True, help="Interleave configs across task/seed")
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run to harness/run.py")
    parser.add_argument("--timeout-s", type=int, default=300, help="Max run duration per cell in seconds")
    return parser.parse_args()

def generate_schedule(tasks, seeds, configs, interleave=True):
    """
    Generates ordered list of (task, seed, config) triples.
    If interleave=True, order is:
      For each task:
        For each seed:
          For each config:
            yield (task, seed, config)
    This prevents temporal drift or provider load shifts from biasing one config.
    """
    schedule = []
    if interleave:
        for t in tasks:
            for s in seeds:
                for c in configs:
                    schedule.append((t, s, c))
    else:
        for c in configs:
            for t in tasks:
                for s in seeds:
                    schedule.append((t, s, c))
    return schedule

def setup_clean_workspace(task_dir, config_id=None, configs_dir="configs"):
    """
    Creates an isolated temporary directory, copies task fixture files,
    and installs the target config's AGENTS.md (if present).
    """
    fixture_dir = task_dir / "fixture"
    temp_dir = Path(tempfile.mkdtemp(prefix=f"te_run_{task_dir.name}_"))
    if fixture_dir.exists():
        shutil.copytree(str(fixture_dir), str(temp_dir), dirs_exist_ok=True)
    if config_id:
        cfg_agents = Path(configs_dir) / config_id / "AGENTS.md"
        if cfg_agents.exists():
            shutil.copy(str(cfg_agents), str(temp_dir / "AGENTS.md"))
    return temp_dir

def run_single_cell(task_id, seed, config_id, block, tasks_dir, configs_dir, runs_dir, model, dry_run, timeout_s):
    task_path = Path(tasks_dir) / task_id
    if not task_path.exists():
        print(f"Warning: Task directory not found: {task_path}", file=sys.stderr)
        return False

    prompt_path = task_path / "prompt.txt"
    judge_path = task_path / "done.ps1"
    if not judge_path.exists():
        judge_path = task_path / "done.sh"

    # Set up clean isolated workspace for this run with config installed
    temp_workspace = setup_clean_workspace(task_path, config_id=config_id, configs_dir=configs_dir)
    
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "harness" / "run.py"),
        "--task-id", task_id,
        "--config-id", config_id,
        "--seed", str(seed),
        "--block", str(block),
        "--repo-dir", str(temp_workspace),
        "--prompt", str(prompt_path),
        "--judge", str(judge_path),
        "--runs-dir", str(runs_dir),
        "--model", model,
        "--timeout-s", str(timeout_s)
    ]
    if dry_run:
        cmd.append("--dry-run")

    print(f"\n========================================================")
    print(f"Executing: Task={task_id} | Seed={seed} | Config={config_id}")
    print(f"Workspace: {temp_workspace}")
    print(f"========================================================")

    success = False
    try:
        proc = subprocess.run(cmd, text=True)
        success = (proc.returncode == 0)
    finally:
        # Clean up workspace
        try:
            shutil.rmtree(temp_workspace)
        except Exception as e:
            print(f"Note: Could not completely remove temp dir {temp_workspace}: {e}", file=sys.stderr)

    return success

def main():
    args = parse_args()
    schedule = generate_schedule(args.tasks, args.seeds, args.configs, interleave=args.interleave)
    total_runs = len(schedule)

    print(f"Interleaved Batch Scheduler: {total_runs} total runs planned.")
    print(f"Configs: {args.configs}")
    print(f"Tasks: {args.tasks}")
    print(f"Seeds: {args.seeds}")
    print(f"Interleaved order: {args.interleave}")

    completed = 0
    for idx, (task_id, seed, config_id) in enumerate(schedule, 1):
        print(f"\n[{idx}/{total_runs}] Running cell: ({task_id}, seed {seed}, config {config_id})")
        ok = run_single_cell(
            task_id=task_id,
            seed=seed,
            config_id=config_id,
            block=args.block,
            tasks_dir=args.tasks_dir,
            configs_dir=args.configs_dir,
            runs_dir=args.runs_dir,
            model=args.model,
            dry_run=args.dry_run,
            timeout_s=args.timeout_s
        )
        if ok:
            completed += 1

    print(f"\nBatch execution finished: {completed}/{total_runs} runs executed successfully.")

if __name__ == "__main__":
    main()
