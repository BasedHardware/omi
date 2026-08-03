# PAPER

Standalone Next.js (App Router) front end for PAPER. No component libraries by design.

| Route | What it is |
| --- | --- |
| `/` | Marketing landing page. Public. |
| `/login` | Sign in with Google (Firebase). Public. |
| `/today` | Today's edition, built from your own record. Requires sign-in. |

## Run it

```sh
npm ci
cp .env.template .env.local   # then fill in the Firebase values
npm run dev                   # http://localhost:3005
```

Sign-in needs real `NEXT_PUBLIC_FIREBASE_*` values — the same Firebase project
`web/app` uses. Without them `/login` and `/today` say so on the page instead of
failing inside the SDK; nothing else on the site is affected.

- Build: `npm run build`
- Lint: `npm run lint`

## How `/today` gets your paper

The browser never calls the Omi API directly. `/today` takes the signed-in reader's
Firebase ID token, sends it to `/api/proxy/v1/paper/{yyyy-mm-dd}` (the local date),
and that route forwards the token to `NEXT_PUBLIC_API_BASE_URL` (default
`https://api.omi.me`). The response is the `Edition` model from
`backend/models/paper.py`, rendered block by block in fixed order — lede, open loops,
counterpoint, the desk, the margin — with absent blocks skipped.

A day with no signal prints `Nothing to print today.` and stops. A failed request
prints the status and the backend's own message. Neither ever prints invented copy.
