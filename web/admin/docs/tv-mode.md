# Admin TV share links

Kiosk wall = Grafana `omi-tv-v2` in the Business org (same board as
`/dashboard`), opened via a secret URL. No custom metrics board. The board
carries revenue, MRR and cost panels, so a share link is finance data:
issuing one requires `finance:read` (on top of `analytics:share`), the link
list redacts the tokens without it, and the kiosk re-checks the issuer still
holds `finance:read` on every view — demote or remove the issuer and their
links stop working.

| Surface | Auth | Role |
| --- | --- | --- |
| `/dashboard` | Firebase admin | Grafana embed (edit chrome) |
| `/dashboard/tv-links` | Firebase admin | Create / list / copy / revoke |
| `/tv/view/<token>` | Capability token | Kiosk Grafana (`&kiosk`) |
| `GET/POST /api/omi/tv-links` | Firebase admin | Manage |
| `DELETE /api/omi/tv-links/[id]` | Firebase admin | Revoke (`await props.params`) |
| `POST /api/grafana/tv-embed` | Capability token | Mint kiosk embed for a validated link |

Optional query on the kiosk URL: `?tv=0.55` (Fire TV scale).

Firestore `admin_tv_links`; doc id = sha256 hex; store `tokenHash` + `token`.
Default TTL 90d. TV tokens unlock the kiosk page only. When the private
Business embed is enabled, the kiosk mints a short-lived embed through
`POST /api/grafana/tv-embed` (token re-validated server-side — including the
issuer's `finance:read` — identity namespaced per link). It never falls back
to the retired Grafana instance or frames Grafana's login page;
revocation/expiry of the link, or the issuer losing `finance:read`, stops new
embeds.

`AuthProvider` must skip admin check/sign-out/redirect on `/tv/view/*`.

Local: `NEXT_PUBLIC_DEV_BYPASS_AUTH=1 npm run dev`. Kiosk without Firestore:
`/tv/view/dev-kiosk`. Mint/revoke still needs `FIREBASE_*` Admin SDK env.
