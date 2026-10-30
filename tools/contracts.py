"""
tools/contracts.py — Canonical Token-Economic Invariants & Templates.

Single source of truth for Project TE-Agent contracts across all platforms:
- OpenCode (AGENTS.md)
- Antigravity (~/.gemini or AGENTS.md)
- Cursor (.cursorrules)
- Claude Code (CLAUDE.md)
- Harness Benchmark Configs (configs/C3)
- npm package (npm-pkg)

All variants enforce the exact same 5 Token-Economic Operating Invariants.
"""

CANONICAL_INVARIANTS = [
    ("1. Never edit or execute without explicit intent",
     "Formulate and state a 1-line hypothesis in your thought or message before executing shell commands or editing code."),
    ("2. Never re-read recent files",
     "If a file was read within the last 3 turns, reuse the context from the conversation history. Do not emit duplicate read calls."),
    ("3. Targeted reads over full reads",
     "When inspecting code, read specific line ranges (StartLine/EndLine) around relevant functions or classes rather than dumping entire files."),
    ("4. Two-strike rule on tool errors",
     "If a tool call fails or times out twice with similar arguments, halt the loop, re-evaluate strategy, or escalate."),
    ("5. Never self-adjudicate success",
     "Completion claims are subject to external verification tests (done.ps1 / done.sh). Do not claim completion unless verification passes cleanly.")
]

CANONICAL_TOOL_PROTOCOLS = """## 2. Tool Card Protocols (Negative & Positive Guidelines)

### Terminal / Command Execution
- **Allowed / Positive**: Run targeted, specific test commands (e.g. `python -m unittest tests/test_*.py` or `npm test`).
- **Forbidden / Negative**: Running unbounded commands, dumping thousands of lines of logs, or running the same failing command repeatedly with trivial whitespace changes.

### File Reading & Searching
- **Allowed / Positive**: Read targeted line ranges (`StartLine`, `EndLine`) when inspecting specific functions or definitions.
- **Forbidden / Negative**: Reading entire multi-hundred-line files repeatedly across successive turns when only one function or section is relevant."""

CANONICAL_STOP_BUDGETS = """## 3. Stop Rules & Budgets
- **Maximum turns per task**: Default budget is 15 turns unless overridden by task spec.
- **Loop threshold**: >= 3 retries on the same error signature triggers immediate termination.
- **Context pruning**: Strip obsolete command output before continuing conversation."""

CANONICAL_DONE_FORMAT = """## 4. Deterministic Completion Format
When a task is finished, the final response MUST include the following exact report block to allow regex parsing by the evaluation harness:

```markdown
## Done
- [x] Task objective satisfied
- [x] Verification checks passed
- Reason: <1-line summary of what was completed>
```"""

def get_contract_text(platform="opencode"):
    """Generate the standardized contract for the specified platform."""
    platform = platform.lower().strip()
    
    invariants_md = "\n".join(
        f"{i+1}. **{title.split('. ', 1)[1] if '. ' in title else title}**: {desc}"
        for i, (title, desc) in enumerate(CANONICAL_INVARIANTS)
    )

    if platform in ("opencode", "c3", "default"):
        header = "# AGENTS: Token Economics & Task Contract\n\n## 1. Operating Invariants"
        return f"{header}\n{invariants_md}\n\n---\n\n{CANONICAL_TOOL_PROTOCOLS}\n\n---\n\n{CANONICAL_STOP_BUDGETS}\n\n---\n\n{CANONICAL_DONE_FORMAT}\n"
    elif platform in ("agy", "antigravity", "gemini"):
        header = "# GEMINI / AGY: Token Economics & Operating Contract\n\n## 1. Operating Invariants"
        return f"{header}\n{invariants_md}\n\n---\n\n{CANONICAL_TOOL_PROTOCOLS}\n\n---\n\n{CANONICAL_STOP_BUDGETS}\n\n---\n\n{CANONICAL_DONE_FORMAT}\n"
    elif platform in ("cursor", ".cursorrules"):
        header = "# Cursor Token-Economic Contract Rules\n\n## 1. Operating Invariants"
        return f"{header}\n{invariants_md}\n\n---\n\n{CANONICAL_TOOL_PROTOCOLS}\n\n---\n\n{CANONICAL_STOP_BUDGETS}\n\n---\n\n{CANONICAL_DONE_FORMAT}\n"
    elif platform in ("claude", "claude.md"):
        header = "# CLAUDE.md: Token Economics & Task Contract\n\n## 1. Operating Invariants"
        return f"{header}\n{invariants_md}\n\n---\n\n{CANONICAL_TOOL_PROTOCOLS}\n\n---\n\n{CANONICAL_STOP_BUDGETS}\n\n---\n\n{CANONICAL_DONE_FORMAT}\n"
    else:
        header = "# AGENTS: Token Economics & Task Contract\n\n## 1. Operating Invariants"
        return f"{header}\n{invariants_md}\n\n---\n\n{CANONICAL_TOOL_PROTOCOLS}\n\n---\n\n{CANONICAL_STOP_BUDGETS}\n\n---\n\n{CANONICAL_DONE_FORMAT}\n"

def get_target_filename(platform="opencode"):
    platform = platform.lower().strip()
    if platform in ("cursor", ".cursorrules"):
        return ".cursorrules"
    elif platform in ("claude", "claude.md"):
        return "CLAUDE.md"
    elif platform in ("agy", "antigravity", "gemini"):
        return "GEMINI.md"
    return "AGENTS.md"
