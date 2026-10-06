/**
 * Next.js instrumentation hook. Located inside `src/` because this app uses a
 * src directory (Next reads `src/instrumentation.ts`).
 *
 * `register()` runs once per server instance before requests are served.
 * Guard on NEXT_RUNTIME === "nodejs" so the Node-only OTel/Azure SDK is never
 * loaded in the Edge runtime.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    const { initObservability } = await import('@/lib/observability');
    await initObservability();
    // First wired custom event (Phase 3): degraded mode → local line only.
    const { trackEvent } = await import('@/lib/events');
    trackEvent('service.start');
  }
}
