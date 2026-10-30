#!/usr/bin/env node

/**
 * te-agent: Ultra-lightweight Zero-Dependency CLI for AI Agent Token Economics.
 * Runs instantly via `npx te-agent` or `npx te-init`.
 * Generates contract-based, anti-loop configuration in under 2 seconds.
 */

const fs = require('fs');
const path = require('path');

const CANONICAL_CONTRACT = `# AGENTS: Token Economics & Task Contract

## 1. Operating Invariants
1. **Never edit or execute without explicit intent**: Formulate and state a 1-line hypothesis in your thought or message before executing shell commands or editing code.
2. **Never re-read recent files**: If a file was read within the last 3 turns, reuse the context from the conversation history. Do not emit duplicate read calls.
3. **Targeted reads over full reads**: When inspecting code, read specific line ranges (StartLine/EndLine) around relevant functions or classes rather than dumping entire files.
4. **Two-strike rule on tool errors**: If a tool call fails or times out twice with similar arguments, halt the loop, re-evaluate strategy, or escalate.
5. **Never self-adjudicate success**: Completion claims are subject to external verification tests (done.ps1 / done.sh). Do not claim completion unless verification passes cleanly.

---

## 2. Tool Card Protocols (Negative & Positive Guidelines)

### Terminal / Command Execution
- **Allowed / Positive**: Run targeted, specific test commands (e.g. \`python -m unittest tests/test_*.py\` or \`npm test\`).
- **Forbidden / Negative**: Running unbounded commands, dumping thousands of lines of logs, or running the same failing command repeatedly with trivial whitespace changes.

### File Reading & Searching
- **Allowed / Positive**: Read targeted line ranges (\`StartLine\`, \`EndLine\`) when inspecting specific functions or definitions.
- **Forbidden / Negative**: Reading entire multi-hundred-line files repeatedly across successive turns when only one function or section is relevant.

---

## 3. Stop Rules & Budgets
- **Maximum turns per task**: Default budget is 15 turns unless overridden by task spec.
- **Loop threshold**: >= 3 retries on the same error signature triggers immediate termination.
- **Context pruning**: Strip obsolete command output before continuing conversation.

---

## 4. Deterministic Completion Format

When a task is finished, the final response MUST include the following exact report block to allow regex parsing by the evaluation harness:

\`\`\`markdown
## Done
- [x] Task objective satisfied
- [x] Verification checks passed
- Reason: <1-line summary of what was completed>
\`\`\`
`;

function detectProjectStack(cwd) {
  if (fs.existsSync(path.join(cwd, 'package.json'))) return 'node';
  if (fs.existsSync(path.join(cwd, 'pyproject.toml')) || fs.existsSync(path.join(cwd, 'requirements.txt'))) return 'python';
  if (fs.existsSync(path.join(cwd, 'Cargo.toml'))) return 'rust';
  if (fs.existsSync(path.join(cwd, 'go.mod'))) return 'go';
  return 'general';
}

function parseCliArgs() {
  const args = process.argv.slice(2);
  let platform = 'opencode';
  let output = '';
  let force = false;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--platform' || a === '-p') platform = args[++i] || 'opencode';
    else if (a === '--output' || a === '-o') output = args[++i] || '';
    else if (a === '--force' || a === '-f') force = true;
    else if (!a.startsWith('-')) platform = a;
  }
  return { platform, output, force };
}

function main() {
  const cwd = process.cwd();
  const stack = detectProjectStack(cwd);
  const { platform, output, force } = parseCliArgs();

  let targetFilename = 'AGENTS.md';
  if (platform === 'cursor') targetFilename = '.cursorrules';
  else if (platform === 'claude') targetFilename = 'CLAUDE.md';
  else if (platform === 'agy') targetFilename = 'GEMINI.md';
  if (output) targetFilename = output;

  const targetPath = path.isAbsolute(targetFilename) ? targetFilename : path.join(cwd, targetFilename);

  console.log('\x1b[36m%s\x1b[0m', '=== TE-Agent: Lean Token-Economics Scaffold ===');
  console.log(`Target: \x1b[32m${platform}\x1b[0m -> ${targetFilename} (Stack: ${stack})`);

  if (fs.existsSync(targetPath) && !force) {
    console.log(`\x1b[33mWarning:\x1b[0m File already exists at ${targetPath}`);
    console.log('Use --force to overwrite.');
    process.exit(0);
  }

  let content = CANONICAL_CONTRACT;
  if (stack === 'node') {
    content = content.replace('python -m unittest tests/test_*.py', 'npm test -- tests/parser.test.js');
  } else if (stack === 'rust') {
    content = content.replace('python -m unittest tests/test_*.py', 'cargo test');
  } else if (stack === 'go') {
    content = content.replace('python -m unittest tests/test_*.py', 'go test ./...');
  }

  fs.writeFileSync(targetPath, content, 'utf8');
  console.log(`\x1b[32mSuccess:\x1b[0m Created lean token-economic contract: \x1b[1m${targetFilename}\x1b[0m`);
  console.log('Your AI coding agent is now contract-bound against token loops.');
}

main();
