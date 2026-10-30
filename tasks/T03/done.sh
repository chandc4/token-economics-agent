#!/usr/bin/env bash
set -e
REPO_DIR="$1"
cd "$REPO_DIR"
python -m unittest test_cache.py