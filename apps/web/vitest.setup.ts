// Silence the pino structured logs during tests. logger.ts reads LOG_LEVEL at
// import time; setupFiles run before the test modules are imported.
process.env.LOG_LEVEL = 'silent';

// jest-dom matchers (toBeInTheDocument, toBeDisabled, …) for component tests (ADR-0011).
// Importing is environment-agnostic; the matchers only act on DOM nodes.
import '@testing-library/jest-dom/vitest';
