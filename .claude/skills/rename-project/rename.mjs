#!/usr/bin/env node
// Rename the AI Accelerator placeholders to a real project name, repo-wide.
//
// Usage: node .claude/skills/rename-project/rename.mjs "<Display Name>" <kebab-slug>
//   e.g. node .claude/skills/rename-project/rename.mjs "Acme Portal" acme-portal
//
// Replaces (longest-first, literal):
//   @ai-accelerator/   -> @<slug>/          (npm package scope)
//   ai-accelerator     -> <slug>            (OTEL names, Docker images, compose, pyproject)
//   AI Accelerator     -> <Display Name>    (titles, headings, docs prose)
//
// Skips: node_modules, .venv, .next, dist, coverage, generated code, lockfiles
// (uv.lock is regenerated with `uv lock` afterwards), and this skill's own folder.
import { readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs';
import { join, relative, dirname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const [display, slug] = process.argv.slice(2);

if (!display || !slug) {
  console.error('Usage: node rename.mjs "<Display Name>" <kebab-slug>');
  process.exit(1);
}
if (!/^[A-Za-z0-9][A-Za-z0-9 &().-]*$/.test(display) || /["\\]/.test(display)) {
  console.error(`Invalid display name "${display}": letters, digits, spaces, & ( ) . - only.`);
  process.exit(1);
}
if (!/^[a-z][a-z0-9-]*[a-z0-9]$/.test(slug) || slug.includes('--') || slug.length > 40) {
  console.error(
    `Invalid slug "${slug}": kebab-case, must start with a letter, end with a letter/digit, ` +
      'no double hyphens, max 40 chars (used in npm scope, OTEL names, Docker tags, pyproject).',
  );
  process.exit(1);
}

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const SELF = resolve(dirname(fileURLToPath(import.meta.url)));
const EXCLUDE_DIRS = new Set([
  'node_modules',
  '.venv',
  '.next',
  'dist',
  'coverage',
  '.git',
  '__pycache__',
  '.pytest_cache',
  'generated',
  'test-results',
  'playwright-report',
]);
const EXCLUDE_FILES = new Set(['uv.lock', 'pnpm-lock.yaml']);

const REPLACEMENTS = [
  ['@ai-accelerator/', `@${slug}/`],
  ['ai-accelerator', slug],
  ['AI Accelerator', display],
];

const changed = [];
const leftovers = [];

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (resolve(full) === SELF || resolve(full).startsWith(SELF + sep)) continue;
    const st = statSync(full);
    if (st.isDirectory()) {
      if (!EXCLUDE_DIRS.has(entry)) walk(full);
      continue;
    }
    if (EXCLUDE_FILES.has(entry)) continue;
    let text;
    try {
      text = readFileSync(full, 'utf8');
    } catch {
      continue;
    }
    if (text.includes('\u0000')) continue; // binary
    let out = text;
    let count = 0;
    for (const [from, to] of REPLACEMENTS) {
      const parts = out.split(from);
      count += parts.length - 1;
      out = parts.join(to);
    }
    if (count > 0) {
      writeFileSync(full, out, 'utf8');
      changed.push(`${relative(ROOT, full)}: ${count}`);
    }
    if (/ai.accelerator/i.test(out)) leftovers.push(relative(ROOT, full));
  }
}

walk(ROOT);
console.log(`Renamed to "${display}" (slug: ${slug})`);
console.log('--- files changed (replacement count) ---');
console.log(changed.join('\n') || '(none)');
console.log('--- files still mentioning the placeholder (should be empty) ---');
console.log(leftovers.join('\n') || '(none)');
console.log('--- remaining manual steps ---');
console.log('1. cd apps/api && uv lock   (lockfile records the distribution name)');
console.log('2. Delete stale build output if present: apps/web/.next');
console.log('3. Remove the "Using this template" section from README.md and delete');
console.log('   .claude/skills/rename-project/ and .claude/commands/rename-project.md');
