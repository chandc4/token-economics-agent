#!/usr/bin/env python3
"""
tools/te_clean.py — Safely clean accumulated benchmark runs and temporary files.
Usage:
  python tools/te_clean.py            # Keeps last 5 runs, deletes older
  python tools/te_clean.py --all      # Deletes all runs
  python tools/te_clean.py --dry-run  # Preview without deleting
"""

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def clean_runs(runs_dir, keep_last=5, dry_run=False):
    if not runs_dir.is_dir():
        print(f"No runs directory at {runs_dir}")
        return

    subdirs = sorted([d for d in runs_dir.iterdir() if d.is_dir()], key=lambda p: p.stat().st_mtime)
    total = len(subdirs)
    if total <= keep_last:
        print(f"Runs directory is clean: {total} runs present (keeping up to {keep_last}).")
        return

    to_delete = subdirs[:total - keep_last]
    print(f"Cleaning {len(to_delete)} older benchmark runs (keeping {keep_last} most recent)...")

    freed_bytes = 0
    for d in to_delete:
        d_size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        freed_bytes += d_size
        if dry_run:
            print(f"  [Dry-Run] Would delete: {d.name} ({round(d_size / 1024, 1)} KB)")
        else:
            try:
                shutil.rmtree(d)
                print(f"  Deleted: {d.name} ({round(d_size / 1024, 1)} KB)")
            except Exception as e:
                print(f"  Could not delete {d.name}: {e}", file=sys.stderr)

    freed_mb = round(freed_bytes / (1024 * 1024), 2)
    print(f"Done. Cleaned {len(to_delete)} runs. Freed ~{freed_mb} MB.")

def main():
    parser = argparse.ArgumentParser(description="Clean accumulated benchmark runs")
    parser.add_argument("--all", action="store_true", help="Delete all runs without keeping any")
    parser.add_argument("--keep", type=int, default=5, help="Number of recent runs to keep (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    keep_count = 0 if args.all else args.keep
    runs_dir = PROJECT_ROOT / "runs"
    clean_runs(runs_dir, keep_last=keep_count, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
