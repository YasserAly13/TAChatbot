import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Produce a self-contained build for Docker (.next/standalone/server.js).
  output: 'standalone',
  // Keep these native/heavy packages out of the bundle so they run as real
  // Node modules at runtime (required for OTel auto-instrumentation and pino;
  // api-logs/api must resolve to the same copies the distro registered its
  // global providers through; the instrumentation packages hook Node
  // internals and must not be bundled).
  serverExternalPackages: [
    '@azure/identity',
    '@azure/monitor-opentelemetry',
    '@opentelemetry/api',
    '@opentelemetry/api-logs',
    '@opentelemetry/instrumentation',
    '@opentelemetry/instrumentation-runtime-node',
    '@opentelemetry/instrumentation-undici',
    'pino',
  ],
  // This app is an independent package in this monorepo (there is a root
  // tooling lockfile AND this app's own pnpm-workspace.yaml). Pin the root to
  // THIS directory so Turbopack (dev) and output file tracing (standalone
  // build) don't mis-infer the repo root from sibling lockfiles.
  turbopack: { root: __dirname },
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
