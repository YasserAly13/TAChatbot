import { expect, test } from '@playwright/test';

/**
 * Smoke e2e — MANUAL/LOCAL ONLY (needs the full stack up: web + api).
 *   make up   (or make dev),  then:  pnpm -C apps/web test:e2e
 */

const TRACE_ID = /[0-9a-f]{32}/;

test('home page pings the api backend through the BFF and renders a trace_id', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'AI Accelerator' })).toBeVisible();

  for (const label of ['Ping backend', 'Info backend']) {
    await page.getByRole('button', { name: label }).click();
  }

  // Each panel renders its trace_id (span.trace-id) once the BFF responds.
  await expect(page.locator('.trace-id').first()).toHaveText(TRACE_ID, { timeout: 15_000 });
});
