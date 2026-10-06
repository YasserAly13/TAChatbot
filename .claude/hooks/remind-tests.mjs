#!/usr/bin/env node
// Stop hook: when application code changed in the working tree without any test file
// changing, surface a reminder (the mechanical version of CLAUDE.md rule 3). Advisory —
// prints a systemMessage and exits 0; the CI `tests-changed-gate` is the enforcing check.
import { execFileSync } from 'node:child_process';

let status = '';
try {
  status = execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8', windowsHide: true });
} catch {
  process.exit(0); // not a git checkout — nothing to say
}

const changed = status
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => line.slice(3).trim().replace(/\\/g, '/'))
  .map((p) => (p.includes(' -> ') ? p.split(' -> ')[1] : p));

const isTest = (p) =>
  /^apps\/api\/tests\//.test(p) || /\.test\.tsx?$/.test(p) || /^apps\/web\/e2e\//.test(p);
const isCode = (p) =>
  /^(apps\/api\/app\/|apps\/web\/src\/)/.test(p) &&
  !isTest(p) &&
  !/api-types\.ts$/.test(p) &&
  !/^apps\/web\/src\/mocks\//.test(p);

const code = changed.filter(isCode);
const tests = changed.filter(isTest);

if (code.length > 0 && tests.length === 0) {
  const message =
    `Reminder (rule 3): ${code.length} application file(s) changed without any test change — ` +
    `${code.slice(0, 5).join(', ')}${code.length > 5 ? ', …' : ''}. ` +
    'Add or update tests before handing over (CI enforces this on PRs).';
  process.stdout.write(JSON.stringify({ systemMessage: message }));
}
process.exit(0);
