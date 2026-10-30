# Project TE-Agent: Token Economics for OpenCode

## 1. Project Mission & Core Objective
This project builds a **Token-Economic Solution & Evaluation Harness for OpenCode**.
Its goal is to replace verbose, costly `/init` conventions with lean, contract-based configurations and verify them through an automated evaluation harness that measurably reduces:
- **Cost per Solved Task (CPST in OTE - Output-Token-Equivalents)**
- **Tool retry rates and repetitive call loops**
- **Attention dilution and prompt bloat**
- **False completion claims ("overclaims")**

*Scope note*: OpenCode is our sole active development, runtime, and measurement target. Once proven and validated here, the framework and findings can be ported to other environments like Antigravity (AGY).

---

## 2. Target Environment & Focus

- **Target CLI & Runtime**: **OpenCode** (single CLI focus).
- **Model Policy**: Single pinned model per comparison block to avoid multi-role attribution contamination and isolate harness/config impact.
- **Operating OS**: Windows 11 (PowerShell & Python standard library).

---

## 3. Core Deliverables

1. **Token-Economic `/init` Template & Generator**:
   - Lean configuration (`AGENTS.md`) designed for OpenCode.
   - Explicit operational invariants and pre-call intent declaration.
   - Negative tool examples (preventing redundant reads and unguided commands).
   - Turn/retry stop budgets and deterministic `## Done` completion reporting.

2. **Automated Evaluation Harness (`harness/`)**:
   - Manages clean repo checkouts per run.
   - Runs tasks via `opencode run` in headless mode.
   - Logs events (`manifest.json`, `events.jsonl`, `done.json`).
   - Executes an independent external judge (`done.ps1` / `done.sh`) isolated outside the repo tree.

3. **Metrics & Statistical Analyzer (`te_analyze.py`)**:
   - Implements `01-METRICS-SPEC.md v0.1`.
   - Normalizes usage to OTE (`w_fresh * in_fresh + w_cache * in_cached + out`).
   - Classifies tool calls (`novel`, `retry`, `repeat`, `denied`).
   - Cluster bootstrap confidence intervals and Holm multiple testing correction.

---

## 4. Ground Rules & Invariants

- **Empirical Rigor First**: No subjective assertions. Every claim must survive an A/A noise-floor baseline test.
- **Single-Model Stability**: Comparisons must hold the model constant across identical seeds to measure config impact cleanly.
- **Kill Criteria**: If candidate configs do not beat the median by more than the measured noise floor, stop and publish the null result.
- **Pure Python**: Core harness and analyzer rely strictly on the Python standard library.
