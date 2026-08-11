'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export const WIDGET_SESSION_REQUEST_EVENT = 'omi.memory.embed.session-request';
export const WIDGET_SESSION_EVENT = 'omi.memory.embed.session';

/**
 * How a framed widget obtains a session.
 *
 * The published embed sandboxes the frame with `allow-scripts` and deliberately
 * without `allow-same-origin`, so the framed document has an opaque origin: every
 * durable browser storage API is denied to it, and Firebase auth therefore
 * cannot establish or restore a session inside it. Relaxing the sandbox is not
 * an option — a document granted both `allow-scripts` and `allow-same-origin`
 * can rewrite its own `sandbox` attribute and escape the restriction entirely.
 *
 * So the host page owns the credential. It mints a short-lived token server-side
 * for the visitor it has already authenticated and hands it to the frame over
 * `postMessage`. The token lives only in this hook's memory for the lifetime of
 * the frame; it is never persisted anywhere, and the widget never sees a durable
 * API key.
 *
 * Messages are validated by `event.source`, not by origin: an opaque-origin
 * sender always reports `event.origin === 'null'`, so an origin allowlist cannot
 * distinguish the host from anyone else. Only the frame's own parent can be the
 * source of a message this widget accepts.
 */
export interface EmbedSession {
  /** True when this document is running inside a frame. */
  framed: boolean;
  /** True while a framed widget is still waiting for the host's first token. */
  awaitingHost: boolean;
  /** The host-provided token, or null when none has arrived. */
  getHostToken: () => string | null;
}

function isFramed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.parent !== window;
  } catch {
    // A cross-origin parent can throw on access; that itself means we are framed.
    return true;
  }
}

export function useEmbedSession(): EmbedSession {
  const [framed, setFramed] = useState(false);
  const [awaitingHost, setAwaitingHost] = useState(false);
  const tokenRef = useRef<string | null>(null);

  useEffect(() => {
    if (!isFramed()) return;
    setFramed(true);
    setAwaitingHost(true);

    function onMessage(event: MessageEvent) {
      // Origin is 'null' under the documented sandbox, so the sender is the
      // only meaningful control.
      if (event.source !== window.parent) return;
      const data = event.data as { type?: string; token?: unknown };
      if (data?.type !== WIDGET_SESSION_EVENT) return;
      tokenRef.current = typeof data.token === 'string' && data.token ? data.token : null;
      setAwaitingHost(false);
    }

    window.addEventListener('message', onMessage);
    // The host may not have been listening when the frame first painted, so ask
    // explicitly rather than relying on the ready event alone.
    window.parent.postMessage({ type: WIDGET_SESSION_REQUEST_EVENT }, '*');
    return () => window.removeEventListener('message', onMessage);
  }, []);

  const getHostToken = useCallback(() => tokenRef.current, []);

  return { framed, awaitingHost, getHostToken };
}
