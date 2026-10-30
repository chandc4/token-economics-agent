#!/usr/bin/env python3
"""
te-analyze 0.1 — JSONL -> metrics -> paired statistics.

Reads a runs/ directory (manifest.json + events.jsonl + done.json per run).
Implements 01-METRICS-SPEC v0.1: sections 4 (OTE), 5 (call classes),
7 (metrics), 8 (noise floor / decision rule), 9 (refusal rule).

Exit codes: 0 ok | 2 token claims unsupported | 3 insufficient data
"""
import argparse, json, math, random, re, statistics, sys
from collections import defaultdict
from pathlib import Path

# Ensure utf-8 encoding on standard streams if supported
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


WINDOW = 3               # §5: prior 3 calls, same stream
SIM_THRESHOLD = 0.85     # §5: fixed, never tuned
MIN_REL_DELTA = 0.10     # §8: practical-significance floor
CONSISTENCY_MIN = 0.70   # §8: direction consistency
OVERRIDE_VOID = 0.10     # §6: >10% overrides voids a block
BOOTSTRAP_N = 10_000
INFERRED_MAX = 0.05      # §9

# ---------------------------------------------------------------- prices

def load_prices(path):
    p = json.loads(Path(path).read_text())
    if "w_fresh" in p and "w_cache" in p:
        return p
    o = p["price_out_per_mtok"]
    return {**p,
            "w_fresh": p["price_in_uncached_per_mtok"] / o,
            "w_cache": p["price_in_cached_per_mtok"] / o}

def ote_of(usage, prices):
    return (prices["w_fresh"] * usage.get("in_fresh", 0)
            + prices["w_cache"] * usage.get("in_cached", 0)
            + usage.get("out", 0))

# ---------------------------------------------------------------- loading

def load_runs(root):
    runs = []
    for d in sorted(Path(root).iterdir()):
        mp = d / "manifest.json"
        if not mp.exists():
            continue
        man = json.loads(mp.read_text())
        ev = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if l.strip()]
        done = json.loads((d / "done.json").read_text()) if (d / "done.json").exists() else {}
        runs.append({"dir": d, "manifest": man, "events": ev, "done": done})
    if not runs:
        sys.exit(f"no runs found under {root}")
    return runs

# ---------------------------------------------------------------- §5 calls

_TOK = re.compile(r"[A-Za-z0-9_./:-]+")

def _tokset(s):
    return set(_TOK.findall(s or ""))

def similar(a, b, thr=SIM_THRESHOLD):
    ta, tb = _tokset(a), _tokset(b)
    if not ta or not tb:
        return float((a or "") == (b or ""))
    return len(ta & tb) / len(ta | tb) >= thr

def classify_calls(events):
    """Adds 'cls' to each call event. Retry beats repeat when both apply."""
    calls = [e for e in events if e.get("ev") == "call"]
    for i, c in enumerate(calls):
        stream = c.get("role", "root")
        stream_prior = [p for p in calls[:i] if p.get("role", "root") == stream]
        prev = stream_prior[-WINDOW:]
        matched = None
        for p in reversed(prev):
            if similar(c.get("args_canon", ""), p.get("args_canon", "")):
                matched = p
                break
        if c.get("result") == "denied":
            cls = "denied"
        elif matched is None:
            cls = "novel"
        elif matched.get("result") in ("error", "timeout", "denied"):
            cls = "retry"
        elif (c.get("args_canon_sha256") == matched.get("args_canon_sha256")
              and matched.get("result") == "ok"):
            cls = "repeat"
        else:
            cls = "novel"
        c["cls"] = cls
        c["matched_seq"] = matched.get("seq") if matched else None

    retries_by_sig = defaultdict(int)
    for c in calls:
        if c["cls"] == "retry":
            retries_by_sig[c.get("args_canon_sha256") or c.get("tool")] += 1
    loops = sum(1 for v in retries_by_sig.values() if v >= 3)
    return calls, loops

# ---------------------------------------------------------------- §7 per run

def run_metrics(run, prices):
    man, ev, done = run["manifest"], run["events"], run["done"]
    turns = [e for e in ev if e.get("ev") == "turn"]
    calls, loops = classify_calls(ev)

    fresh = sum(t["usage"].get("in_fresh", 0) for t in turns)
    cached = sum(t["usage"].get("in_cached", 0) for t in turns)
    out = sum(t["usage"].get("out", 0) for t in turns)
    ote = sum(ote_of(t["usage"], prices) for t in turns)
    ote_comp = sum(ote_of(t["usage"], prices) for t in turns
                   if t.get("req", {}).get("compaction"))

    n = len(calls)
    n_err = sum(1 for c in calls if c.get("result") in ("error", "timeout", "denied"))
    n_retry = sum(1 for c in calls if c["cls"] == "retry")
    n_rep = sum(1 for c in calls if c["cls"] == "repeat")
    n_den = sum(1 for c in calls if c["cls"] == "denied")

    solved = done.get("solved", done.get("exit_code") == 0)
    claims = bool(done.get("claims_done", False))

    return {
        "run_id": man.get("run_id", run["dir"].name),
        "task_id": man["task_id"], "config_id": man["config_id"],
        "seed": man.get("seed", 0), "block": man.get("block", 0),
        "ote": ote, "ote_compaction": ote_comp,
        "in_fresh": fresh, "in_cached": cached, "out": out,
        "n_turns": len(turns), "n_calls": n,
        "n_error": n_err, "n_retry": n_retry, "n_repeat": n_rep,
        "n_denied": n_den, "loop_incidents": loops,
        "solved": bool(solved), "claims_done": claims,
        "overclaim": claims and not solved,
        "overridden": bool(done.get("overridden", False)),
        "wall_clock_ms": done.get("duration_ms", 0),
        "exact_tokens": man.get("capabilities", {}).get("exact_tokens", False),
        "attribution": man.get("attribution", "exact"),
        "dirty": man.get("repo", {}).get("dirty", False),
        "model_reported": man.get("model", {}).get("reported"),
        "pricing_window": man.get("pricing", {}).get("window"),
        "tool_results": man.get("capabilities", {}).get("tool_results", False),
        "tool_args": man.get("capabilities", {}).get("tool_args", False),
    }

# ---------------------------------------------------------------- §7 per config

def _rate(a, b):
    return (a / b) if b else None

def agg(rows):
    n = len(rows)
    solved = [r for r in rows if r["solved"]]
    ote_total = sum(r["ote"] for r in rows)
    per_task = defaultdict(list)
    for r in rows:
        per_task[r["task_id"]].append(r)

    task_cpst = []
    for t, rs in per_task.items():
        s = sum(r["ote"] for r in rs)
        ns = sum(1 for r in rs if r["solved"])
        if ns:
            task_cpst.append(s / ns)

    nc = sum(r["n_calls"] for r in rows)
    return {
        "config_id": rows[0]["config_id"], "n_runs": n,
        "n_solved": len(solved),
        "success_rate": _rate(len(solved), n),
        "cpst": (ote_total / len(solved)) if solved else float("inf"),
        "cpst_median_task": statistics.median(task_cpst) if task_cpst else None,
        "p90_task_ote": _p90([sum(r["ote"] for r in rs) for rs in per_task.values()]),
        "ote_total": ote_total,
        "ote_compaction_share": _rate(sum(r["ote_compaction"] for r in rows), ote_total),
        "in_fresh": sum(r["in_fresh"] for r in rows),
        "in_cached": sum(r["in_cached"] for r in rows),
        "out": sum(r["out"] for r in rows),
        "n_calls": nc,
        "retry_rate": _rate(sum(r["n_retry"] for r in rows), nc),
        "repeat_rate": (_rate(sum(r["n_repeat"] for r in rows), nc)
                        if all(r["tool_results"] for r in rows) else None),
        "waste_rate": (_rate(sum(r["n_retry"] + r["n_repeat"] for r in rows), nc)
                       if all(r["tool_results"] for r in rows) else None),
        "call_validity_rate": (1 - _rate(sum(r["n_error"] for r in rows), nc)) if nc else None,
        "loop_incidents": sum(r["loop_incidents"] for r in rows),
        "overclaim_rate": _rate(sum(1 for r in rows if r["overclaim"]),
                                sum(1 for r in rows if r["claims_done"])),
        "override_frac": _rate(sum(1 for r in rows if r["overridden"]), n),
        "wall_clock_s": sum(r["wall_clock_ms"] for r in rows) / 1000,
        "exact_tokens": all(r["exact_tokens"] for r in rows),
        "pricing_window": sorted({r["pricing_window"] for r in rows}),
        "model_reported": sorted({r["model_reported"] for r in rows}),
    }

def _p90(xs):
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.9 * len(s)))]

# ---------------------------------------------------------------- §8 paired

def pair_rows(rows, cfg_a, cfg_b):
    """Interleaved pairs share (task, seed). Returns {task: [rel_delta, ...]}."""
    idx = {}
    for r in rows:
        idx[(r["task_id"], r["seed"], r["config_id"])] = r
    out = defaultdict(list)
    for (task, seed, cfg), a in idx.items():
        if cfg != cfg_a:
            continue
        b = idx.get((task, seed, cfg_b))
        if b is None or a["ote"] <= 0:
            continue
        out[task].append((b["ote"] - a["ote"]) / a["ote"])
    return out

def cluster_bootstrap(task_deltas, n=BOOTSTRAP_N, seed=0):
    """Resample TASKS, keep all seeds within a task (§8)."""
    tasks = [t for t, ds in task_deltas.items() if ds]
    if len(tasks) < 3:
        return None, None
    per_task = {t: statistics.median(task_deltas[t]) for t in tasks}
    rng = random.Random(seed)
    meds = []
    for _ in range(n):
        s = [per_task[rng.choice(tasks)] for _ in tasks]
        meds.append(statistics.median(s))
    meds.sort()
    return meds[int(0.025 * n)], meds[int(0.975 * n) - 1]

def compare(rows, cfg_a, cfg_b, seed=0):
    td = pair_rows(rows, cfg_a, cfg_b)
    usable = {t: ds for t, ds in td.items() if ds}
    if not usable:
        return {"usable": False, "reason": "no paired runs"}
    per_task = {t: statistics.median(ds) for t, ds in usable.items()}
    med = statistics.median(per_task.values())
    lo, hi = cluster_bootstrap(usable, seed=seed)
    same = sum(1 for d in per_task.values() if (d > 0) == (med > 0))
    consistency = same / len(per_task)
    sd_task = statistics.pstdev(list(per_task.values())) if len(per_task) > 1 else 0.0
    p_boot = None
    if lo is not None:
        p_boot = _boot_p(usable, med, seed=seed)
    sig = (lo is not None and (lo > 0 or hi < 0)
           and abs(med) >= MIN_REL_DELTA and consistency >= CONSISTENCY_MIN)
    ci_status = "ok" if lo is not None else "insufficient_task_clusters (< 3 tasks)"
    return {
        "usable": True, "a": cfg_a, "b": cfg_b,
        "directionality": "rel_delta = (B - A) / A. Negative values indicate B saved tokens compared to A.",
        "median_rel_delta": med, "ci95": (lo, hi), "ci_status": ci_status, "p_boot": p_boot,
        "consistency": consistency, "n_tasks": len(per_task),
        "n_pairs": sum(len(ds) for ds in usable.values()),
        "sd_delta": sd_task, "significant": sig
    }

def _boot_p(task_deltas, med, n=BOOTSTRAP_N, seed=0):
    """Two-sided bootstrap p under H0: median Δ = 0, resampling tasks."""
    tasks = list(task_deltas)
    per_task = {t: statistics.median(task_deltas[t]) for t in tasks}
    rng = random.Random(seed + 1)
    extreme = 0
    for _ in range(n):
        s = [per_task[rng.choice(tasks)] for _ in tasks]
        m = statistics.median(s)
        if (m >= abs(med)) or (m <= -abs(med)):
            extreme += 1
    return min(1.0, extreme / n)

def holm(pvals):
    order = sorted(pvals, key=lambda x: x[1])
    m, running, adj = len(order), 0.0, {}
    for i, (label, p) in enumerate(order):
        running = max(running, min(1.0, (m - i) * p))
        adj[label] = running
    return adj

# ---------------------------------------------------------------- §8 power

def required_r(sd_rel, delta_rel=MIN_REL_DELTA):
    if sd_rel <= 0:
        return 1
    return math.ceil((1.96 * sd_rel / (delta_rel / 2)) ** 2)

def pilot_cv(rows, cfg):
    per_task = defaultdict(list)
    for r in rows:
        if r["config_id"] == cfg:
            per_task[r["task_id"]].append(r["ote"])
    cvs, spreads = {}, {}
    for t, xs in per_task.items():
        if len(xs) >= 2 and statistics.mean(xs) > 0:
            m = statistics.mean(xs)
            s = statistics.stdev(xs)
            cvs[t] = s / m
            spreads[t] = (m, s)
    return cvs, spreads

# ---------------------------------------------------------------- report

def fmt(x, p=3):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if math.isinf(x):
            return "inf"
        return f"{x:.{p}f}"
    return str(x)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--prices", required=True)
    ap.add_argument("--configs", nargs="*", help="subset of config_ids")
    ap.add_argument("--compare", nargs=2, action="append", metavar=("A", "B"))
    ap.add_argument("--claim", choices=["cost", "success"], default="success")
    ap.add_argument("--pilot-config", help="config for CV / R estimate")
    ap.add_argument("--bootstrap-seed", type=int, default=0)
    ap.add_argument("--json-out", help="write machine summary here")
    args = ap.parse_args()

    prices = load_prices(args.prices)
    runs = load_runs(args.runs)
    rows = [run_metrics(r, prices) for r in runs]

    dirty = [r["run_id"] for r in rows if r["dirty"]]
    if dirty:
        print(f"WARNING: {len(dirty)} dirty runs present, excluded: {dirty[:5]}", file=sys.stderr)
        rows = [r for r in rows if not r["dirty"]]

    cfgs = args.configs or sorted({r["config_id"] for r in rows})

    # §9 refusal rule
    if args.claim == "cost":
        bad = [r["config_id"] for r in rows if not r["exact_tokens"]
               or r["attribution"] == "inferred"]
        inferred_frac = _rate(sum(1 for r in rows if r["attribution"] == "inferred"), len(rows))
        if bad or (inferred_frac or 0) > INFERRED_MAX:
            print("TOKEN CLAIMS UNSUPPORTED FOR THIS ADAPTER", file=sys.stderr)
            print(f"  configs lacking exact tokens: {sorted(set(bad))}", file=sys.stderr)
            print(f"  inferred attribution: {fmt(inferred_frac)} (> {INFERRED_MAX})", file=sys.stderr)
            return 2

    # integrity: model / pricing window must be constant within a block
    for c in cfgs:
        cs = [r for r in rows if r["config_id"] == c]
        if len({r["model_reported"] for r in cs}) > 1:
            print(f"BLOCK VOID ({c}): model.reported varies {sorted({r['model_reported'] for r in cs})}",
                  file=sys.stderr)
            return 3
        if len({r["pricing_window"] for r in cs}) > 1:
            print(f"BLOCK VOID ({c}): pricing window varies; costs not comparable",
                  file=sys.stderr)
            return 3

    print("# te-analyze report\n")
    print(f"runs: {len(rows)} | configs: {len(cfgs)} | claim mode: {args.claim}\n")

    aggs = {c: agg([r for r in rows if r["config_id"] == c]) for c in cfgs}

    hdr = ["config", "runs", "solved", "succ", "CPST", "CPST_med", "p90_ote",
           "retry", "repeat", "waste", "valid", "loops", "overclaim", "ovr", "comp%"]
    print("| " + " | ".join(hdr) + " |")
    print("|" + "|".join(["---"] * len(hdr)) + "|")
    for c in cfgs:
        a = aggs[c]
        print("| " + " | ".join([
            c, fmt(a["n_runs"]), fmt(a["n_solved"]), fmt(a["success_rate"], 2),
            fmt(a["cpst"], 0), fmt(a["cpst_median_task"], 0), fmt(a["p90_task_ote"], 0),
            fmt(a["retry_rate"], 2), fmt(a["repeat_rate"], 2), fmt(a["waste_rate"], 2),
            fmt(a["call_validity_rate"], 2), fmt(a["loop_incidents"]),
            fmt(a["overclaim_rate"], 2), fmt(a["override_frac"], 2),
            fmt(a["ote_compaction_share"], 3),
        ]) + " |")
    print("\nRepeat/waste n/a means `tool_results` capability is missing, not zero (§5).")
    print("CPST is only quotable jointly with success_rate (§7).")

    # ---- §4 token split, so a win can be attributed to the right mechanism
    print("\n## Token split (§4)\n")
    print("| config | in_fresh | in_cached | out | cache_share | OTE total |")
    print("|---|---|---|---|---|---|")
    for c in cfgs:
        a = aggs[c]
        tot_in = a["in_fresh"] + a["in_cached"]
        print(f"| {c} | {a['in_fresh']} | {a['in_cached']} | {a['out']} | "
              f"{fmt(_rate(a['in_cached'], tot_in), 2)} | {fmt(a['ote_total'], 0)} |")
    print("\ncache_share moving instead of out/in_fresh is a prefix-stability win,")
    print("not an efficiency win. Report them as different claims.")

    # ---- §6 void blocks
    for c in cfgs:
        a = aggs[c]
        if a["override_frac"] is not None and a["override_frac"] > OVERRIDE_VOID:
            print(f"\nBLOCK VOID ({c}): overrides {fmt(a['override_frac'],2)} > {OVERRIDE_VOID}")
            return 3

    # ---- §8 paired comparisons
    comparisons = []
    if args.compare:
        print("\n## Paired comparisons (§8)\n")
        print("| A -> B | n_tasks | n_pairs | median rel Δ | 95% CI (cluster) "
              "| consistency | p_boot | sig |")
        print("|---|---|---|---|---|---|---|---|")
        raw_p = []
        for a_id, b_id in args.compare:
            r = compare(rows, a_id, b_id, seed=args.bootstrap_seed)
            if not r["usable"]:
                print(f"| {a_id} -> {b_id} | - | - | - | - | - | - | {r['reason']} |")
                continue
            ci = r["ci95"]
            ci_s = f"[{fmt(ci[0],3)}, {fmt(ci[1],3)}]" if ci[0] is not None else "n/a"
            p = r.get("p_boot")
            raw_p.append((f"{a_id}->{b_id}", p))
            print(f"| {a_id} -> {b_id} | {r['n_tasks']} | {r['n_pairs']} | "
                  f"{fmt(r['median_rel_delta'],3)} | {ci_s} | {fmt(r['consistency'],2)} | "
                  f"{fmt(p,3)} | {'YES' if r['significant'] else 'no'} |")
            comparisons.append({"a": a_id, "b": b_id, **r})

        # Holm across confirmatory comparisons only (§8: <=3)
        if len(raw_p) > 1 and all(p is not None for _, p in raw_p):
            adj = holm(raw_p)
            print("\nHolm-adjusted p (confirmatory set):")
            for label, _ in raw_p:
                print(f"  {label}: {fmt(adj[label], 3)}")
            if len(raw_p) > 3:
                print("  WARNING: >3 confirmatory comparisons. Screen-only from here (§8).")
        elif len(raw_p) > 1:
            print("\np_boot unavailable — patch compare() before trusting multi-way claims.")

    # ---- §8 pilot: noise floor and R
    if args.pilot_config:
        cvs, spreads = pilot_cv(rows, args.pilot_config)
        print(f"\n## Noise floor (§8) — config {args.pilot_config}\n")
        print("| task | n | mean OTE | sd | CV |")
        print("|---|---|---|---|---|")
        for t in sorted(spreads):
            m, s = spreads[t]
            print(f"| {t} | {len([r for r in rows if r['config_id']==args.pilot_config and r['task_id']==t])} "
                  f"| {fmt(m,0)} | {fmt(s,0)} | {fmt(cvs[t],3)} |")
        med_cv = statistics.median(cvs.values()) if cvs else None
        if med_cv is not None:
            r_req = required_r(med_cv)
            print(f"\nmedian CV = {fmt(med_cv,3)}")
            print(f"required runs per cell (delta=10%): R = {r_req}")
            if med_cv > 0.25:
                print("VERDICT: CV > 0.25 — judge or environment is unstable.")
                print("         Fix done.sh / dep cache / network before framework work.")
            elif r_req > 8:
                print("VERDICT: R > 8 — underpowered at 6 configs.")
                print("         Cut config count or raise delta and label 'suggestive'.")
            else:
                print("VERDICT: design is viable at this variance.")
        else:
            print("Insufficient repeated runs for CV (need >=2 seeds per task).")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "schema": "te-report/0.1",
            "claim_mode": args.claim,
            "aggregates": aggs,
            "comparisons": comparisons,
            "n_runs": len(rows),
        }, indent=2, default=str))
        print(f"\nwrote {args.json_out}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
