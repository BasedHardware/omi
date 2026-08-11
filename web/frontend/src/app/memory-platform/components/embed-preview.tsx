'use client';

import { useEffect, useState } from 'react';
import MemoryWidget, { WIDGET_READY_EVENT, WIDGET_RESIZE_EVENT } from './memory-widget';

/**
 * Live preview of the embeddable widget.
 *
 * The widget renders here in demo mode and posts the same typed, credential-free
 * UI events a framed instance posts. This page listens for them with the exact
 * origin and source checks the published snippet documents, so the messaging
 * contract is exercised rather than only described.
 *
 * It renders in-page rather than in an iframe on purpose: the published embed
 * frames the widget from the *host's* origin with `allow-scripts` and without
 * `allow-same-origin`, and an opaque-origin frame cannot run the session code
 * this app's shared layout loads. The framing snippet below the preview is the
 * contract; this is the rendered surface.
 */
export default function EmbedPreview() {
  const [lastEvent, setLastEvent] = useState<string>('waiting');

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      // A frame sandboxed without allow-same-origin posts from the opaque
      // origin "null"; accept only that, or this page's own origin.
      if (event.origin !== 'null' && event.origin !== window.location.origin) return;
      const data = event.data as { type?: string; height?: number };
      if (data?.type === WIDGET_READY_EVENT) setLastEvent(WIDGET_READY_EVENT);
      if (data?.type === WIDGET_RESIZE_EVENT) setLastEvent(WIDGET_RESIZE_EVENT);
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-[#0d0d0d]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-neutral-500">
          live preview
        </span>
        <span className="font-mono text-[11px] text-neutral-600">{lastEvent}</span>
      </div>
      <div className="h-[420px]">
        <MemoryWidget demo />
      </div>
    </div>
  );
}
