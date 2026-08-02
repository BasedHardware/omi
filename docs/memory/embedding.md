---
title: Embed Omi Memory
description: Safely place a memory surface inside another product.
---

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
  sandbox="allow-scripts allow-same-origin"
  style="width:100%;height:560px;border:0"
></iframe>
```

Set `Content-Security-Policy: frame-ancestors https://your-app.example` on the embedded page. Use the exact parent origins you control.

## Server proxy

Your server should authenticate the visitor, validate the tenant, bound the query, and forward the request to `/v1/memory/platform/search`. Keep writes separate and user-initiated. Never forward an arbitrary upstream URL or arbitrary memory owner from the browser.

## postMessage

If the frame needs to resize or notify the parent, use typed events and verify `event.origin` before accepting them. Send UI state such as `memory.embed.ready` or `memory.embed.resize`; do not send bearer tokens or unrestricted memory payloads.

## zkr and local state

Local zkr or SQLite can hold capture state, a cache, or a pending upload. It is not the authority. Only backend-acknowledged records should be applied as authoritative local replica state.
