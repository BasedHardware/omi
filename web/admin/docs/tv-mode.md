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
| `POST /api/grafana/tv-embed` | Capability token | Mint kiosk embed for a validated link |

Optional query on the kiosk URL: `?tv=0.55` (Fire TV scale). While the
legacy board is still framed, `&platform=macos|mobile` selects that legacy
platform board; the private v2 embed is the single combined canonical board
and ignores `platform`.

Firestore `admin_tv_links`; doc id = sha256 hex; store `tokenHash` + `token`.
Default TTL 90d. TV tokens unlock the kiosk page only. While the private
Grafana cutover flag is off and the legacy board still serves anonymous
readers, the kiosk keeps framing legacy `/grafana/d/omi-tv`. Once the cutover
is enabled — or legacy goes private for any reason — the kiosk mints a
short-lived Business embed through `POST /api/grafana/tv-embed` (token
re-validated server-side, identity namespaced per link) and never frames
Grafana's login page; revocation/expiry of the link stops new embeds.

`AuthProvider` must skip admin check/sign-out/redirect on `/tv/view/*`.

Local: `NEXT_PUBLIC_DEV_BYPASS_AUTH=1 npm run dev`. Kiosk without Firestore:
`/tv/view/dev-kiosk`. Mint/revoke still needs `FIREBASE_*` Admin SDK env.
