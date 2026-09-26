# Omi Frontend

Next.js web app (App Router) deployed as Cloud Run service **`frontend`** at
[https://h.omi.me](https://h.omi.me). It hosts the public shared-conversation
share pages (`/chat/:id`, `/conversations/:id`) plus the public storefront
pages: the apps marketplace (`/apps`), `/create-app`, `/wrapped`, and
`/unlimited`.

This is **not** the signed-in web client — that is `web/app` (app.omi.me).

## Stack

- Next.js (App Router), TypeScript, Tailwind CSS
- Radix UI / shadcn-style components
- Firebase (auth/Firestore), Algolia (search), Redis (caching)
- Package manager: **npm** (`package-lock.json`)

## Development

```bash
npm ci
cp .env.template .env.local   # fill in values
npm run dev                   # http://localhost:3000
```

Scripts: `dev`, `build`, `start`, `test` (node --test, `src/__tests__`),
`lint`, `lint:fix`, `lint:format`. CI runs lint + build via
`.github/workflows/web-checks.yml`.

Environment variables are documented in `.env.template`.

## Deployment

Pushes to `main` or `development` under `web/frontend/**` trigger
`.github/workflows/gcp_frontend.yml`, which builds `web/frontend/Dockerfile`
and deploys to Cloud Run following `config/public-build-contract.json`
(target `frontend`, service `frontend`, prod URL `https://h.omi.me`).
Environments: `development` and `prod` only — there is no staging tier.
There is no docker-compose setup.

## Notes

- Public share URLs use `/conversations/:id`; the internal pages/components
  still live under `src/app/memories/`. `next.config.mjs` keeps both URL
  spaces alive with a `/memories/*` → `/conversations/*` redirect and a
  `/conversations/*` → `/memories/*` rewrite.
