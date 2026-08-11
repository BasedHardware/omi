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

If the frame needs to resize or notify the parent, use typed events and verify `event.origin` before accepting them. Send UI state such as `omi.memory.embed.ready` or `omi.memory.embed.resize`; do not send bearer tokens or unrestricted memory payloads.

A frame sandboxed without `allow-same-origin` posts from the opaque origin `"null"`, so check for that value explicitly rather than loosening the sandbox:

```js
const OMI_ORIGIN = 'https://h.omi.me';

window.addEventListener('message', (event) => {
  if (event.origin !== OMI_ORIGIN && event.origin !== 'null') return;
  if (event.source !== frame.contentWindow) return;
  if (event.data?.type !== 'omi.memory.embed.resize') return;
  frame.style.height = `${Number(event.data.height) || 560}px`;
});
```

## Credentials

The embedded surface must never hold a durable Omi API key. Issue MCP keys at
`/memory-platform/keys`, keep them in your server's secret store, and let the proxy
attach them. The raw key is shown exactly once, at creation; after that only its prefix
is visible.

## zkr and local state

Local zkr or SQLite can hold capture state, a cache, or a pending upload. It is not the authority. Only backend-acknowledged records should be applied as authoritative local replica state.
