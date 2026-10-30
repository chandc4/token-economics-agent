"""
tests/test_te_agent.py — Regression & Verification Test Suite for TE-Agent.
Tests:
  1. Call stream classification (novel, repeat, retry, denied) with interleaved stream roles.
  2. Truthiness token extraction (0 value preservation).
  3. Paired statistical comparison & bootstrap directionality.
  4. Contract templates synchronization across platforms.
"""

import json
import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from te_analyze import classify_calls, pair_rows, cluster_bootstrap, compare, ote_of
from harness.run import _extract_token_int
from tools.contracts import get_contract_text, CANONICAL_INVARIANTS

class TestCallClassification(unittest.TestCase):
    def test_novel_call(self):
        events = [
            {"ev": "call", "seq": 0, "role": "root", "tool": "read_file",
             "args_canon": "path=calc.py", "args_canon_sha256": "h1", "result": "ok"}
        ]
        calls, loops = classify_calls(events)
        self.assertEqual(calls[0]["cls"], "novel")
        self.assertEqual(loops, 0)

    def test_repeat_within_window(self):
        events = [
            {"ev": "call", "seq": 0, "role": "root", "tool": "read_file",
             "args_canon": "path=calc.py", "args_canon_sha256": "h1", "result": "ok"},
            {"ev": "call", "seq": 1, "role": "root", "tool": "run_command",
             "args_canon": "cmd=pytest", "args_canon_sha256": "h2", "result": "ok"},
            {"ev": "call", "seq": 2, "role": "root", "tool": "read_file",
             "args_canon": "path=calc.py", "args_canon_sha256": "h1", "result": "ok"}
        ]
        calls, loops = classify_calls(events)
        self.assertEqual(calls[0]["cls"], "novel")
        self.assertEqual(calls[1]["cls"], "novel")
        self.assertEqual(calls[2]["cls"], "repeat")

    def test_repeat_outside_window(self):
        # 4 different calls between repeats (window size is 3)
        events = [
            {"ev": "call", "seq": 0, "role": "root", "tool": "read_file",
             "args_canon": "path=calc.py", "args_canon_sha256": "h1", "result": "ok"},
            {"ev": "call", "seq": 1, "role": "root", "tool": "run_command",
             "args_canon": "cmd=t1", "args_canon_sha256": "h2", "result": "ok"},
            {"ev": "call", "seq": 2, "role": "root", "tool": "run_command",
             "args_canon": "cmd=t2", "args_canon_sha256": "h3", "result": "ok"},
            {"ev": "call", "seq": 3, "role": "root", "tool": "run_command",
             "args_canon": "cmd=t3", "args_canon_sha256": "h4", "result": "ok"},
            {"ev": "call", "seq": 4, "role": "root", "tool": "run_command",
             "args_canon": "cmd=t4", "args_canon_sha256": "h5", "result": "ok"},
            {"ev": "call", "seq": 5, "role": "root", "tool": "read_file",
             "args_canon": "path=calc.py", "args_canon_sha256": "h1", "result": "ok"}
        ]
        calls, loops = classify_calls(events)
        self.assertEqual(calls[5]["cls"], "novel")

    def test_interleaved_subagent_stream_isolation(self):
        # Root makes a call, then subagent makes 4 calls, then root repeats.
        # Root should recognize its own prior call in the same stream!
        events = [
            {"ev": "call", "seq": 0, "role": "root", "tool": "read_file",
             "args_canon": "path=calc.py", "args_canon_sha256": "h1", "result": "ok"},
            {"ev": "call", "seq": 1, "role": "subagent_1", "tool": "search",
             "args_canon": "q=1", "args_canon_sha256": "s1", "result": "ok"},
            {"ev": "call", "seq": 2, "role": "subagent_1", "tool": "search",
             "args_canon": "q=2", "args_canon_sha256": "s2", "result": "ok"},
            {"ev": "call", "seq": 3, "role": "subagent_1", "tool": "search",
             "args_canon": "q=3", "args_canon_sha256": "s3", "result": "ok"},
            {"ev": "call", "seq": 4, "role": "root", "tool": "read_file",
             "args_canon": "path=calc.py", "args_canon_sha256": "h1", "result": "ok"}
        ]
        calls, loops = classify_calls(events)
        self.assertEqual(calls[4]["cls"], "repeat", "Interleaved subagent calls must not evict root stream history")

    def test_two_strike_retry_loop(self):
        # 1 initial failure + 3 retries = 3 retries, triggering loop incident threshold (>= 3)
        events = [
            {"ev": "call", "seq": 0, "role": "root", "tool": "run_command",
             "args_canon": "cmd=build", "args_canon_sha256": "h1", "result": "error"},
            {"ev": "call", "seq": 1, "role": "root", "tool": "run_command",
             "args_canon": "cmd=build", "args_canon_sha256": "h1", "result": "error"},
            {"ev": "call", "seq": 2, "role": "root", "tool": "run_command",
             "args_canon": "cmd=build", "args_canon_sha256": "h1", "result": "error"},
            {"ev": "call", "seq": 3, "role": "root", "tool": "run_command",
             "args_canon": "cmd=build", "args_canon_sha256": "h1", "result": "error"}
        ]
        calls, loops = classify_calls(events)
        self.assertEqual(calls[1]["cls"], "retry")
        self.assertEqual(calls[2]["cls"], "retry")
        self.assertEqual(calls[3]["cls"], "retry")
        self.assertEqual(loops, 1)

class TestTokenExtractionTruthiness(unittest.TestCase):
    def test_zero_preservation(self):
        # in_fresh is explicitly 0, should NOT fall through to prompt_tokens or default
        d = {"in_fresh": 0, "prompt_tokens": 500}
        val = _extract_token_int(d, ["in_fresh", "prompt_tokens"], default=999)
        self.assertEqual(val, 0)

        # in_cached is None, should fall through
        d2 = {"in_cached": None, "cached_tokens": 120}
        val2 = _extract_token_int(d2, ["in_cached", "cached_tokens"], default=0)
        self.assertEqual(val2, 120)

class TestStatisticalComparison(unittest.TestCase):
    def test_bootstrap_directionality(self):
        # Candidate B saves 50% compared to baseline A
        rows = [
            {"task_id": "T01", "seed": 1, "config_id": "C0a", "ote": 1000, "solved": True, "n_calls": 5},
            {"task_id": "T01", "seed": 1, "config_id": "C3", "ote": 500, "solved": True, "n_calls": 3},
            {"task_id": "T02", "seed": 1, "config_id": "C0a", "ote": 2000, "solved": True, "n_calls": 8},
            {"task_id": "T02", "seed": 1, "config_id": "C3", "ote": 1000, "solved": True, "n_calls": 4},
            {"task_id": "T03", "seed": 1, "config_id": "C0a", "ote": 3000, "solved": True, "n_calls": 10},
            {"task_id": "T03", "seed": 1, "config_id": "C3", "ote": 1500, "solved": True, "n_calls": 5},
        ]
        comp = compare(rows, "C0a", "C3", seed=42)
        self.assertTrue(comp["usable"])
        self.assertAlmostEqual(comp["median_rel_delta"], -0.5)
        self.assertEqual(comp["ci_status"], "ok")
        self.assertLess(comp["ci95"][1], 0)

    def test_small_task_cluster_guardrail(self):
        # Only 2 tasks: cluster bootstrap must return None CI and inform reason
        rows = [
            {"task_id": "T01", "seed": 1, "config_id": "C0a", "ote": 1000, "solved": True, "n_calls": 5},
            {"task_id": "T01", "seed": 1, "config_id": "C3", "ote": 500, "solved": True, "n_calls": 3},
            {"task_id": "T02", "seed": 1, "config_id": "C0a", "ote": 2000, "solved": True, "n_calls": 8},
            {"task_id": "T02", "seed": 1, "config_id": "C3", "ote": 1000, "solved": True, "n_calls": 4},
        ]
        comp = compare(rows, "C0a", "C3")
        self.assertIsNone(comp["ci95"][0])
        self.assertEqual(comp["ci_status"], "insufficient_task_clusters (< 3 tasks)")
        self.assertFalse(comp["significant"])

class TestContractInvariants(unittest.TestCase):
    def test_all_platforms_share_5_invariants(self):
        platforms = ["opencode", "agy", "cursor", "claude"]
        for p in platforms:
            text = get_contract_text(p)
            for i in range(1, 6):
                self.assertIn(f"{i}.", text, f"Platform {p} must include Invariant #{i}")

if __name__ == "__main__":
    unittest.main()
