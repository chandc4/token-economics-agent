# 01-METRICS-SPEC: Token Economics & Agent Evaluation Specification
**Version:** 0.1  
**Status:** Canonical Reference  
**Applicability:** OpenCode, Antigravity, and Multi-Runtime LLM Coding Agents

---

## 1. Executive Summary

This specification formalizes the metrics, event log schemas, statistical tests, and cost functions used by **Project TE-Agent**. Its primary objective is to define a mathematically rigorous, reproducible framework for comparing coding agent configurations (prompt contracts, system instructions, and tool interfaces) while controlling for stochastic model variance and caching dynamics.

---

## 2. Token Normalization: Output-Token-Equivalent (OTE)

Because different LLM providers price input, cache read, and output tokens at radically different rates, raw token sums are deceptive. TE-Agent normalizes all compute to **Output-Token-Equivalents (OTE)**:

$$\text{OTE} = w_{\text{fresh}} \cdot T_{\text{in\_fresh}} + w_{\text{cache}} \cdot T_{\text{in\_cached}} + 1.0 \cdot T_{\text{out}}$$

Where default canonical weights are derived from standard commercial frontier model ratios:
- $w_{\text{fresh}} = 0.25$ (1 input token = 0.25 output tokens, reflecting a 4:1 price ratio)
- $w_{\text{cache}} = 0.025$ (1 cached input token = 0.025 output tokens, reflecting a 40:1 ratio)
- $w_{\text{out}} = 1.00$

### Exact USD Cost Calculation
When a pricing table (`prices.json`) is supplied with model-specific rates per million tokens ($P_{\text{fresh}}, P_{\text{cache}}, P_{\text{out}}$):

$$\text{Cost}_{\text{USD}} = \frac{T_{\text{in\_fresh}} \cdot P_{\text{fresh}} + T_{\text{in\_cached}} \cdot P_{\text{cache}} + T_{\text{out}} \cdot P_{\text{out}}}{1,000,000}$$

---

## 3. Primary Metric: Cost per Solved Task (CPST)

The benchmark's ultimate North Star metric is **Cost per Solved Task (CPST)** in OTE:

$$\text{CPST} = \frac{\sum_{i=1}^{N} \text{OTE}_i}{\sum_{i=1}^{N} \mathbb{I}(\text{solved}_i)}$$

Where:
- $N$ is the total number of trial runs across the task cohort.
- $\mathbb{I}(\text{solved}_i) \in \{0, 1\}$ is determined strictly by the **independent external judge** (`done.ps1` / `done.sh`), never by the agent's self-reported text.
- If no tasks are solved, $\text{CPST} = \infty$.

---

## 4. Tool Call Taxonomy & Stream Classification

Every tool call event in `events.jsonl` is assigned exactly one taxonomic category evaluated against the preceding context window of size $W = 3$ turns:

1. **`novel`**: The first issuance of a unique command or read of a specific target path/symbol within window $W$.
2. **`retry`**: An immediate successive invocation of the same tool with identical or trivially modified arguments following an `error` or non-zero exit code.
3. **`repeat`**: Re-reading or re-executing an identical target within window $W \le 3$ following a successful (`ok`) execution, violating the context cache invariant.
4. **`denied`**: A call rejected by system permissions, circuit breakers, or security guards.

### Repeat Rate ($R_{\text{repeat}}$) & Waste Score
$$\text{Waste Rate} = \frac{\sum (\text{Calls}_{\text{repeat}} + \text{Calls}_{\text{retry}})}{\text{Total Calls}}$$

---

## 5. Discipline Index ($D \in [0, 100]$)

The discipline index measures adherence to token-economic invariants:
- **Baseline**: 100 points.
- **Repeat Violation Penalty**: -15 points per duplicate read within 3 turns.
- **Consecutive Error Penalty**: -20 points per 2-strike tool failure.
- **Untargeted Full-Dump Penalty**: -10 points per reading >200 lines without line ranges.
- **Floor**: $\max(0, D)$.

---

## 6. Event Schema (`events.jsonl`)

Every execution step emits a JSONL record conforming to this schema:

```json
{
  "ts": "2026-10-30T11:00:00.000000Z",
  "run_id": "T01_C3_r01_20261030_110000",
  "task_id": "T01",
  "config_id": "C3",
  "turn": 1,
  "ev": "tool_call",
  "tool": "read_file",
  "args": {"Path": "calc/parser.py", "StartLine": 1, "EndLine": 50},
  "status": "ok",
  "duration_ms": 42,
  "tokens": {
    "in_fresh": 450,
    "in_cached": 1200,
    "out": 85
  }
}
```

---

## 7. Statistical Comparison & Decision Rules

1. **A/A Baseline Noise Gate**: Prior to claiming any config superiority, an A/A test ($C0a$ vs $C0a$) across $\ge 5$ seeds must establish the ambient variance. If Coefficient of Variation $\text{CV} > 0.25$, sample size must increase.
2. **Paired Cluster Bootstrap**: Differences in CPST between Candidate $C$ and Baseline $B$ are computed with clustered bootstrapping over task IDs (1,000 resamples) to generate 95% Confidence Intervals.
3. **Holm-Bonferroni Correction**: When testing multiple candidate arms ($C1, C2, C3$), family-wise error rate is controlled at $\alpha = 0.05$.
