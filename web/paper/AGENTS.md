# web/paper

Standalone Next.js App Router app for PAPER. `/` markets it, `/login` signs in with
Firebase, `/today` prints the reader's edition. Spec: `docs/product/paper/SPEC.md`.

- Run: `npm ci && npm run dev` (3005). Build: `npm run build`. Lint: `npm run lint`.
  Sign-in needs the `NEXT_PUBLIC_FIREBASE_*` values in `.env.template`.
- Auth and `src/app/api/proxy/` mirror `web/app`: same env names, same ID-token
  forwarding. Change them together.
- `/today` renders `Edition` from `backend/models/paper.py`. Never invent a block —
  absent is omitted, empty prints "Nothing to print today.", failure prints the error.
- Styling is plain CSS in `globals.css` mirroring `backend/templates/paper.html` — no
  utility classes, no component library, no vendored fonts. Change both or they drift.
- Next 16 has breaking changes from earlier versions; check `node_modules/next/dist/docs/`
  before trusting remembered APIs.
- Never add purple (`INV-UI-1`). Never add a direct LLM provider SDK, URL, or key under
  `web/` (`web-llm-gateway-only`) — route through the Omi gateway.
