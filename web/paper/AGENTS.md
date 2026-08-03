# web/paper

Marketing landing page for PAPER. Standalone Next.js App Router app — `web/` has no
monorepo tooling, so this shares nothing with the other four web packages.

- Product spec and design rationale: `docs/product/paper/SPEC.md`.
- Run: `npm ci && npm run dev` (port 3005). Build: `npm run build`. Lint: `npm run lint`.
- Next 16 has breaking changes from earlier versions; check `node_modules/next/dist/docs/`
  before trusting remembered APIs.
- Styling is plain CSS in `src/app/globals.css`, not utility classes — this is a
  typographic surface and it deliberately mirrors the edition template at
  `backend/templates/paper.html`. Change both together or they drift.
- No component library, no vendored fonts: the serif and mono stacks are system fonts.
- Never add purple (`INV-UI-1`). Never add a direct LLM provider SDK, URL, or key under
  `web/` (`web-llm-gateway-only`) — route through the Omi gateway.
