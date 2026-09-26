# Admin TV share links

Kiosk wall = Grafana `omi-tv` (same board as `/dashboard`), opened via a
secret URL. No custom metrics board.

| Surface | Auth | Role |
| --- | --- | --- |
| `/dashboard` | Firebase admin | Grafana embed (edit chrome) |
| `/dashboard/tv-links` | Firebase admin | Create / list / copy / revoke |
| `/tv/view/<token>` | Capability token | Kiosk Grafana (`&kiosk`) |
| `GET/POST /api/omi/tv-links` | Firebase admin | Manage |
| `DELETE /api/omi/tv-links/[id]` | Firebase admin | Revoke (`await props.params`) |

Optional query on the kiosk URL: `?tv=0.55` (Fire TV scale), `&platform=macos|mobile`.

Firestore `admin_tv_links`; doc id = sha256 hex; store `tokenHash` + `token`.
Default TTL 90d. TV tokens unlock the kiosk page only — they do not change
Grafana's own auth. Live Grafana is already anonymously readable at
`/grafana/d/omi-tv`; the share link is a revocable, login-free wrapper.

`AuthProvider` must skip admin check/sign-out/redirect on `/tv/view/*`.

Local: `NEXT_PUBLIC_DEV_BYPASS_AUTH=1 npm run dev`. Kiosk without Firestore:
`/tv/view/dev-kiosk`. Mint/revoke still needs `FIREBASE_*` Admin SDK env.
