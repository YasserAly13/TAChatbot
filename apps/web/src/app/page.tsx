'use client';

import { useState } from 'react';

interface PanelState {
  loading: boolean;
  traceId?: string;
  data?: unknown;
  error?: string;
}

type PanelKey = 'backend' | 'infoBackend';

const ENDPOINTS: Record<PanelKey, { label: string; path: string }> = {
  backend: { label: 'Ping backend', path: '/api/ping-backend' },
  infoBackend: { label: 'Info backend', path: '/api/info-backend' },
};

// Two button/panel groups over the ONE path (web → api): ping (liveness)
// and info (a consolidated health · version · runtime/server report).
const GROUPS: ReadonlyArray<{ title: string; keys: readonly PanelKey[] }> = [
  { title: 'Ping — liveness', keys: ['backend'] },
  { title: 'Info — health · version · server', keys: ['infoBackend'] },
];

/** Derives a panel's visual status from its state (presentation only). */
function panelStatus(state: PanelState): 'loading' | 'ok' | 'error' | 'idle' {
  if (state.loading) return 'loading';
  if (state.error) return 'error';
  if (state.data !== undefined) return 'ok';
  return 'idle';
}

const STATUS_LABEL: Record<ReturnType<typeof panelStatus>, string> = {
  loading: 'Loading',
  ok: 'OK',
  error: 'Error',
  idle: 'Idle',
};

/** Renders a single panel's body — extracted to avoid a nested ternary. */
function PanelBody({ state }: Readonly<{ state: PanelState }>) {
  if (state.error) {
    return <p className="error">Error: {state.error}</p>;
  }
  if (state.data === undefined) {
    return <p className="empty">No response yet — press the button above to call this service.</p>;
  }
  return (
    <>
      <div>
        <span className="trace-label">trace_id</span>
        <span className="trace-id">{state.traceId ?? '(none)'}</span>
      </div>
      <pre>{JSON.stringify(state.data, null, 2)}</pre>
    </>
  );
}

export default function Home() {
  const [panels, setPanels] = useState<Record<PanelKey, PanelState>>({
    backend: { loading: false },
    infoBackend: { loading: false },
  });

  async function call(key: PanelKey) {
    setPanels((p) => ({ ...p, [key]: { loading: true } }));
    try {
      // Same-origin BFF call only — the browser never talks to the api directly.
      const res = await fetch(ENDPOINTS[key].path, {
        headers: { accept: 'application/json' },
      });
      const traceId = res.headers.get('x-trace-id') ?? undefined;
      const data = await res.json();
      setPanels((p) => ({
        ...p,
        [key]: {
          loading: false,
          traceId:
            traceId ??
            (typeof data === 'object' && data && 'trace_id' in data
              ? String((data as { trace_id: unknown }).trace_id)
              : undefined),
          data,
        },
      }));
    } catch (err) {
      setPanels((p) => ({
        ...p,
        [key]: {
          loading: false,
          error: err instanceof Error ? err.message : 'request failed',
        },
      }));
    }
  }

  return (
    <main>
      <h1>AI Accelerator</h1>
      <p>
        Each button calls a same-origin Next route handler (the BFF). The BFF calls the api backend
        server-side and forwards the same <code>x-trace-id</code> across the hop. The{' '}
        <strong>Ping</strong> row checks liveness; the <strong>Info</strong> row reports the
        backend&apos;s health, version, and runtime details.
      </p>

      {GROUPS.map((group) => (
        <section className="group" key={group.title}>
          <h2>{group.title}</h2>

          <div className="buttons">
            {group.keys.map((key) => (
              <button
                key={key}
                onClick={() => call(key)}
                disabled={panels[key].loading}
                aria-busy={panels[key].loading}
              >
                {panels[key].loading && <span className="spinner" aria-hidden="true" />}
                {ENDPOINTS[key].label}
              </button>
            ))}
          </div>

          <div className="panels">
            {group.keys.map((key) => {
              const status = panelStatus(panels[key]);
              return (
                <section
                  className={`panel${status === 'ok' ? ' is-ok' : ''}${status === 'error' ? ' is-error' : ''}`}
                  key={key}
                >
                  <h3>
                    {ENDPOINTS[key].label}
                    <span
                      className={`status${status === 'ok' ? ' is-ok' : ''}${status === 'error' ? ' is-error' : ''}`}
                    >
                      {STATUS_LABEL[status]}
                    </span>
                  </h3>
                  <PanelBody state={panels[key]} />
                </section>
              );
            })}
          </div>
        </section>
      ))}
    </main>
  );
}
