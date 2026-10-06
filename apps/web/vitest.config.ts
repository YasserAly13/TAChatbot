import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // Node by default (lib + BFF route handlers). Component tests opt into jsdom per file
    // with `// @vitest-environment jsdom` at the top (ADR-0011).
    environment: 'node',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./vitest.setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      reportsDirectory: 'coverage',
      include: ['src/**/*.ts', 'src/components/**/*.tsx'],
      exclude: [
        'src/**/*.{test,spec}.{ts,tsx}',
        'src/instrumentation.ts',
        'src/**/*.d.ts',
        // Generated from docs/reference/openapi.json — not code to cover.
        'src/lib/api-types.ts',
        // Fixtures, not logic.
        'src/mocks/**',
      ],
    },
  },
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
});
