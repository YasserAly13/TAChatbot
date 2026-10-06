#!/usr/bin/env node
// PostToolUse hook (Edit|Write): format the file Claude just touched with the repo's own
// formatter — prettier (JS/TS/JSON/MD/YAML/CSS), ruff (Python under apps/api), bicep format.
// Portable: plain node, repo-relative paths, never fails the tool call (always exits 0).
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

const root = process.cwd();

function readStdin() {
  try {
    return readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

function run(cmd, args) {
  try {
    execFileSync(cmd, args, { cwd: root, stdio: 'ignore', windowsHide: true });
  } catch {
    /* formatting is best-effort */
  }
}

let payload = {};
try {
  payload = JSON.parse(readStdin() || '{}');
} catch {
  process.exit(0);
}
const file = payload?.tool_input?.file_path;
if (!file || !existsSync(file)) process.exit(0);

const rel = path.relative(root, file).replace(/\\/g, '/');
if (rel.startsWith('..') || rel.includes('node_modules/') || rel.includes('/.venv/'))
  process.exit(0);

const ext = path.extname(file).toLowerCase();
const prettierBin = path.join(root, 'node_modules', 'prettier', 'bin', 'prettier.cjs');

if (ext === '.py' && rel.startsWith('apps/api/')) {
  run('uv', ['run', '--directory', 'apps/api', 'ruff', 'format', file]);
  run('uv', ['run', '--directory', 'apps/api', 'ruff', 'check', '--fix', '--quiet', file]);
} else if (ext === '.bicep') {
  run('bicep', ['format', file]);
} else if (
  ['.ts', '.tsx', '.js', '.mjs', '.cjs', '.json', '.md', '.yml', '.yaml', '.css'].includes(ext) &&
  existsSync(prettierBin)
) {
  run(process.execPath, [prettierBin, '--write', '--log-level', 'silent', file]);
}
process.exit(0);
