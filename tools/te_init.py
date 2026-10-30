#!/usr/bin/env python3
"""
tools/te_init.py — Token-Economic Config Generator for OpenCode / Antigravity / Cursor / Claude.
Generates canonical, contract-based configurations with zero prompt bloat.
"""

import argparse
import sys
from pathlib import Path

# Import canonical contract definitions
try:
    from tools.contracts import get_contract_text, get_target_filename
except ImportError:
    from contracts import get_contract_text, get_target_filename

def main():
    parser = argparse.ArgumentParser(description="Generate lean Token-Economic contract configuration")
    parser.add_argument("--platform", "-p", default="opencode", choices=["opencode", "agy", "cursor", "claude"],
                        help="Target platform (default: opencode)")
    parser.add_argument("--output", "-o", default="", help="Custom output file path")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing configuration")
    args = parser.parse_args()

    content = get_contract_text(args.platform)
    target_name = args.output if args.output else get_target_filename(args.platform)
    out_path = Path(target_name).resolve()

    if out_path.exists() and not args.force:
        sys.exit(f"File {out_path} already exists. Use --force to overwrite.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Successfully generated {args.platform} token-economic contract at:\n  -> {out_path}")
    print(f"Contract Size: {len(content.encode('utf-8'))} bytes (5 Invariants, Tool Cards, Stop Rules, Verification)")

if __name__ == "__main__":
    main()
