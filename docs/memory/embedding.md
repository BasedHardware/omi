---
title: Embed Omi Memory
description: Safely place a memory surface inside another product.
---

A rendered example of the widget, framed exactly as documented here, is at
[`/memory-platform/embed`](https://h.omi.me/memory-platform/embed).

The recommended embed architecture is:

```text
browser -> your origin -> Omi API -> backend-authoritative memory
```

Keep Omi credentials on your server. Do not put API keys in browser JavaScript, localStorage, public environment variables, or an iframe URL.

## Iframe boundary

Host the memory UI on your own origin and embed it with a strict sandbox:

```html
<iframe
  src="https://your-app.example/omi-memory"
  title="Omi memory"
  loading="lazy"
  referrerpolicy="strict-origin-when-cross-origin"
  sandbox="allow-scripts"
  style="width:100%;height:560px;border:0"
></iframe>
```

Set `Content-Security-Policy: frame-ancestors https://your-app.example` on the embedded page. Use the exact parent origins you control.

Never add `allow-same-origin` alongside `allow-scripts`. A document granted both can rewrite its own `sandbox` attribute and escape the restriction entirely.

## Server proxy

Your server should authenticate the visitor, validate the tenant, bound the query, and forward the request to `/v1/memory/platform/search`. Keep writes separate and user-initiated. Never forward an arbitrary upstream URL or arbitrary memory owner from the browser.

## postMessage

If the frame needs to resize or notify the parent, use typed events. Send UI state such as `omi.memory.embed.ready` or `omi.memory.embed.resize`; do not send unrestricted memory payloads.

**Validate the sender, not the origin.** A frame sandboxed without `allow-same-origin` has an opaque origin, so every message it posts carries `event.origin === "null"` — never your Omi origin. An origin allowlist therefore cannot tell the frame apart from any other opaque-origin sender, and comparing against an `https://` literal silently drops every event. The effective control is `event.source === frame.contentWindow`, because only that frame's window can be its own `contentWindow`.

```js
const frame = document.querySelector('#omi-memory');

window.addEventListener('message', (event) => {
  // The sandboxed frame's origin is the opaque 'null', so validate the SENDER.
  if (event.source !== frame.contentWindow) return;
  if (event.data?.type !== 'omi.memory.embed.resize') return;
  frame.style.height = `${Number(event.data.height) || 560}px`;
});
```

## Sessions

The same opaque origin that makes origin checks useless also denies the frame cookies, `localStorage`, and IndexedDB, so the framed widget **cannot establish a session on its own**. Do not relax the sandbox to fix this: a document granted both `allow-scripts` and `allow-same-origin` can rewrite its own `sandbox` attribute and escape the restriction entirely.

Instead the host page owns the credential. The frame asks for one with `omi.memory.embed.session-request`; the host mints a short-lived token server-side for the visitor it has already authenticated and replies with `omi.memory.embed.session`:

```js
window.addEventListener('message', async (event) => {
  if (event.source !== frame.contentWindow) return;
  if (event.data?.type !== 'omi.memory.embed.session-request') return;

  // Minted server-side for the visitor you already authenticated.
  const { token } = await fetch('/api/omi-session').then((r) => r.json());
  frame.contentWindow.postMessage(
    { type: 'omi.memory.embed.session', token },
    '*', // an opaque-origin frame cannot be addressed by origin
  );
});
```

The frame holds the token in memory for its lifetime only and never writes it to durable storage.

## Credentials

The embedded surface must never hold a durable Omi API key. `/v1/memory/platform/*`
authenticates with Firebase ID tokens and rejects MCP and Developer key families, so
there is no durable server key for it — forward the visitor's own refreshable session.
MCP keys, issued at `/memory-platform/keys`, are for MCP clients; keep them in your
server's secret store. The raw key is shown exactly once, at creation; after that only
its prefix is visible.

## zkr and local state

Local zkr or SQLite can hold capture state, a cache, or a pending upload. It is not the authority. Only backend-acknowledged records should be applied as authoritative local replica state.
