import { defineConfig, devices } from '@playwright/test';

/**
 * MANUAL / LOCAL ONLY — intentionally NOT part of the CI gate.
 *
 * Requires the full stack running (web :3000 + api :8000):
 *   make up         # docker compose, or
 *   make dev        # local concurrent
 * then:  pnpm -C apps/web test:e2e
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: process.env.WEB_BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
