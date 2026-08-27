# web/app architecture

Signed-in Omi web client: React 19 on `@tschk/moonshine`. Destinations live in
`src/app`; product code lives in `src/features/<domain>` and shared kernel in
`src/shared`.

## Layers (inside a feature)

| Path | Holds | Must not |
|---|---|---|
| `model.ts` (and other pure helpers) | grouping, ids, parsing | React, `fetch`, `./api` |
| `api.ts` | HTTP for this domain | UI |
| `ui/` | components | ad-hoc `fetch`; thick helpers |
| hooks (`useX.ts`) | current React state / orchestration | a second data-layer |

Cross-feature and `src/app` imports use the feature's public `index.ts` only.
`src/shared` does not import `src/features`. Enforced by
`scripts/check-feature-imports.ts` (part of `bun run check`).

## Kernel vs features

- `src/shared/api/client.ts` — `fetchWithAuth` and authorized blob/audio headers
- `src/shared/ui` — Toast, dialogs, input, maps, startup modals (no feature imports)
- `src/lib` — firebase, cache, utils, generated OpenAPI types (not yet moved)
- `src/components/layout` — shell chrome (may import features)
- Tailwind `content` is `src/**` so feature class names reach `styles.css`
- `src/hooks/useAsyncResource.ts`, `useLocalStorage`, `useRequestOwner`,
  `useScrollEdges` — generic hooks, not a domain

Writable moonshine stores hold lists and session state written from the UI
(goals, tasks, people, conversations, recaps, memories, chat, search,
notifications, knowledge graph, Gemini Live, goal advice). Read-only fetches
use `useAsyncResource` (`useHomeTasks`, `useGoalDetail` history).

## Features (grow as domains move)

See `src/features/*/ARCHITECTURE.md` once a folder exceeds twelve source files.
The destination map is unchanged: `/home` is hub+chat, `/conversations` includes
recaps, `/connectors` is apps+services.
