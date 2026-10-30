# AGENTS Contract: Invariants & Pre-Call Intent

## 1. Operating Invariants
1. **Never execute or edit without explicit intent**: Formulate and state a 1-line hypothesis in your thought or message before invoking terminal commands or modifying files.
2. **Never self-adjudicate success**: Completion is strictly determined by external test judges. Do not claim success unless verification criteria pass cleanly.

## 2. Deterministic Completion Format
When a task is finished, your final response MUST include this exact report block:

```markdown
## Done
- [x] Task objective satisfied
- [x] Verification checks passed
- Reason: <1-line summary of what was completed>
```
