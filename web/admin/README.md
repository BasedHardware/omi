# Omi Admin Dashboard

The dashboard at `admin.omi.me` is a Next.js app. It presents the internal
admin UI, authenticates the browser with Firebase, and exposes same-origin
Next route handlers under `app/api/`. Those handlers authorize the caller and
then read from Firebase or call the Omi API and vendor APIs. Browser code
never receives the server credentials.

## Run locally

```bash
cd web/admin
cp .env.example .env.local
npm ci
```

For UI work, set the following in `.env.local` and start the app:

```dotenv
NEXT_PUBLIC_DEV_BYPASS_AUTH=1
```

```bash
npm run dev
```

Open <http://localhost:3000/dashboard>. The bypass supplies the fixed local
identity `dev-admin` to the client and protected route handlers; it is
hard-disabled for production builds. It is useful for layout and interaction
work, but API cards whose backing service is not configured will show errors.
Do not put production credentials in `.env.local`.

## Test against a local backend

For a working Omi API integration, run the backend locally using its
[developer guide](../../backend/AGENTS.md) and use a separate development or
offline data environment. Set these values in `web/admin/.env.local`:

```dotenv
NEXT_PUBLIC_DEV_BYPASS_AUTH=1
NEXT_PUBLIC_OMI_API_URL=http://localhost:8080
OMI_API_SECRET_KEY=<the same value as backend ADMIN_KEY>
```

The dashboard sends both the base key and a token formed from that key plus
the authenticated UID. With the bypass, the UID is `dev-admin`, which the
local backend accepts when its `ADMIN_KEY` matches `OMI_API_SECRET_KEY`.
Admin actions can mutate the backend and its data stores, so this mode must
never point at production.

Routes that read or write Firestore also need `FIREBASE_PROJECT_ID`,
`FIREBASE_CLIENT_EMAIL`, and `FIREBASE_PRIVATE_KEY` for a non-production
Firebase project. Pages that use an external system need only that system's
credential from `.env.example` (for example Stripe, PostHog, Typesense,
GoAffPro, or Anthropic). Firebase client variables are needed when testing the
real login flow instead of the bypass.

## Checks

Run these before opening a PR:

```bash
npm run check
npm run build
```

`check` runs ESLint, TypeScript, and the Vitest unit suite. Use `npm run
test:watch` while adding or editing tests. The GitHub web check runs the same
three checks for changes under `web/admin/`, then builds the app.

## Authentication and permissions

In normal operation, the browser signs in with Firebase Google or email
authentication. The client and every protected route require the user UID to
exist at `adminData/{uid}` in Firestore. Server route handlers verify the
Firebase ID token with the Firebase Admin SDK; they do not trust the
client-side check alone.

For local work, permissions break down as follows:

- UI-only work needs no cloud, Firebase, or vendor access when the development
  bypass is enabled.
- Real login testing needs a Firebase Authentication user and a matching
  `adminData/{uid}` document in a non-production project.
- Data-backed pages need a Firebase service account that can read the
  appropriate non-production Firestore project, plus only the service
  credentials for the page under test.
- Local Omi API work needs a local backend `ADMIN_KEY`; do not request or use
  the production key.
- Deployment through GitHub Actions needs permission to merge or push to the
  deployment branch and approval for the target GitHub Environment. The
  workflow's deployment identity, not a developer workstation, needs access
  to Artifact Registry, Cloud Run, and the Cloud Run runtime secrets. A direct
  GCP deployment would additionally require equivalent Cloud Run, Artifact
  Registry, service-account impersonation, and Secret Manager access.

## Delivery path and current gaps

`.github/workflows/gcp_admin.yml` deploys changes under `web/admin/` on pushes
to `main` or `development`. It builds the Docker image from this directory,
bakes public `NEXT_PUBLIC_*` values into the image, injects server secrets at
Cloud Run runtime, and shifts 100% of traffic to the new revision. The
repository does not define a pull-request preview deployment, local Firebase
emulators, seeded admin data, or browser end-to-end tests. Those are the next
meaningful investments once the local UI and backend loop above is in regular
use.
