# AGENTS Contract: Tool Cards & Smart Reads

## 1. Operating Invariants
1. **Never execute or edit without explicit intent**: Formulate and state a 1-line hypothesis before running commands or editing files.
2. **Never re-read recent files**: If a file was read within the last 3 turns, reuse the context. Do not emit duplicate read calls.

## 2. Tool Card Protocols (Negative & Positive Guidelines)

### Terminal / Command Execution
- **Allowed / Positive**: Run targeted, specific test commands:
  ```powershell
  python -m unittest test_calculator.py
  ```
- **Forbidden / Negative**: Running unbounded commands or repeatedly running the exact same failing command with trivial spacing changes.

### File Reading & Searching
- **Allowed / Positive**: Read targeted line ranges (StartLine, EndLine) or inspect specific definitions.
- **Forbidden / Negative**: Reading entire multi-hundred-line files repeatedly across successive turns when only one function or section is relevant.

## 3. Deterministic Completion Format
When a task is finished, your final response MUST include this exact report block:

```markdown
## Done
- [x] Task objective satisfied
- [x] Verification checks passed
- Reason: <1-line summary of what was completed>
```
