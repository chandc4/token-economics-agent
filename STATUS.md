# Project Status

**Version:** 0.1 (Alpha / Prototype)

TE-Agent is an experimental, measurement-first framework for token-economics in coding agents. It is **not** production-ready.

## What works
- End-to-end harness on OpenCode (real tokens, tools, external judge).
- Statistical analyzer (OTE, call taxonomy, bootstrap, Holm correction).
- A/A noise-floor gate and power estimation.
- Web cockpit for session audit and contract scaffolding.
- Real-time sentinel (advisory).

## Known limitations
- Cost-reduction hypothesis is **unproven** on real tasks (small, noisy sample; easy tasks).
- Environment variance exceeds the A/A gate (median CV ≈ 0.29 > 0.25).
- Judges are Windows-first (`done.ps1`); Unix `done.sh` is partial.
- Dashboard is advisory; it cannot block tool calls.
- Only 3 toy task fixtures; no multi-repo or multi-language support yet.

## Roadmap
- v0.2: Stabilize environment, scale benchmark matrix, publish A/A + candidate results.
- v0.3: Enforcement layer (runtime hooks/plugins), budget alerts, export/trends.
- v0.4: Cross-platform judges, multi-language tasks, community task corpus.

See `GEMINI.md` for the full mission and kill criteria.