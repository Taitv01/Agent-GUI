// Exercise the installed Gemini policy parser/engine without an LLM request.
import assert from 'node:assert/strict';
import { readdir } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [bundle, policy] = process.argv.slice(2);
const core = (await readdir(bundle)).find(name => /^core-.*\.js$/.test(name));
const { loadPoliciesFromToml, PolicyEngine, ApprovalMode } =
  await import(pathToFileURL(path.join(bundle, core)).href);
const loaded = await loadPoliciesFromToml([policy], () => 4);
assert.deepEqual(loaded.errors, []);
const engine = new PolicyEngine({
  rules: loaded.rules, nonInteractive: true, approvalMode: ApprovalMode.AUTO_EDIT,
});
for (const command of [
  'pytest', 'pytest -q tests', 'python -m pytest -q', 'py -m pytest',
  'python3 -m unittest discover', 'python -m compileall src',
  '.\\.venv\\Scripts\\python.exe -m pytest', './.venv/bin/python -m pytest',
  'git status --short', 'git diff --check', 'npm test',
]) {
  assert.equal((await engine.check({ name: 'run_shell_command', args: { command } })).decision,
    'allow', command);
}
for (const command of [
  'python -c "print(1)"', 'pytest-malicious', 'git reset --hard',
  'pytest; git reset --hard', 'pytest > result.txt',
]) {
  assert.notEqual((await engine.check({ name: 'run_shell_command', args: { command } })).decision,
    'allow', command);
}
const reviewer = new PolicyEngine({
  rules: loaded.rules, nonInteractive: true, approvalMode: ApprovalMode.PLAN,
});
assert.notEqual((await reviewer.check({
  name: 'run_shell_command', args: { command: 'pytest' },
})).decision, 'allow');
console.log('Gemini policy checks passed');
