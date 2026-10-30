# Contributing to TE-Agent

TE-Agent is an experimental, measurement-first framework. Contributions are welcome.

## Ground rules
- Pure Python stdlib for core harness/analyzer. No new runtime dependencies without discussion.
- Every claim must be measurable. Prefer adding a test or a benchmark cell over asserting behavior.
- Keep contracts lean. The point is to *reduce* instruction bloat, not add to it.

## Development setup
```powershell
python -m pytest tests/test_te_agent.py
python tools/te_doctor.py
```

## How to contribute
1. Open an issue describing the problem or proposal.
2. Fork and create a feature branch.
3. Add or update tests for behavior changes.
4. Run `python tools/te_doctor.py` and ensure it reports HEALTHY.
5. Submit a PR with a clear summary and, if relevant, benchmark evidence.

## Areas we need help with
- Harder task fixtures (multi-file, ambiguous bugs).
- Unix `done.sh` judges and cross-platform support.
- Enforcement layer (OpenCode hooks/plugins).
- Dashboard UX and export features.
- Ports to Cursor/Claude Code/Aider runtimes.