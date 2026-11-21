# Compact Home feed

Default Home renders `/v1/home/feed` cards through `HomeFeedProvider`, separately
from `ConversationProvider` history and detail caches. Search, folder, date,
speaker, starred and discarded views retain their existing APIs during migration.
Cards carry display fields and an opaque revision; they carry no transcript,
source notes, episode member IDs or membership receipts.

Cached card shells paint immediately without source titles/previews; the first remote page supplies display text. Idle warming targets seven days
and stops at eight requests, 350 cards or a conservative 512 KiB display budget.
Scroll continuation starts within two viewport heights of the bottom. One flight
owns a cursor; partial pages may advance it, failures retain a retryable position,
and a partial response never proves history exhaustion. Account/filter/disposal
generations reject late responses and late cache writes.

The account/policy-scoped card cache persists redacted shells only; unverified text cannot survive an offline restart. It never populates conversation detail history.
An explicit refresh replaces the loaded window: a newest page cannot validate
older cached text. Known source mutations immediately suppress affected text and
revalidate the loaded window with the same request/card/byte bounds. Pending
source deletion redacts episode display text until membership can be reconciled.
Full member IDs for episode Delete come only from opened episode detail.

An absent endpoint (404) or explicit `409 home_feed_preparation_required` selects
the compatible Home path. Only that readiness signal starts preparation: three
`POST /v1/home/feed/prepare` calls one second apart, then a thirty-second cooldown.
The active budget is ten minutes or sixty calls, renewable by reader interaction
or explicit refresh; three consecutive failures stop retries until renewal.
Preparation runs only while default Home is visible and never blocks first paint.
A completed preparation is adopted at the top of Home, on re-entry or on explicit
refresh; a scrolled reader keeps the compatible view until that boundary. Network,
authentication, decode and server failures do not select compatibility success.

A card opens immediately using a display seed. Existing conversation detail loads
its transcript/notes; episode detail fetches its saved sections/member cards.
Omitted transcript remains unknown. Episode seed loading/failure is visible, and
Delete cannot operate until authoritative membership arrives. Existing episode
rows have no Home long-press/swipe mutation menu; their detail keeps Delete.

Hermetic coverage: `test/providers/home_feed_provider_test.dart`, the card case
in `test/perf/home_after_detail_perf_test.dart`, and the seed-loading case in
`test/widgets/episode_page_delete_test.dart`. Widget timings do not establish
phone raster cost or production latency; verify a seeded device journey with
agent-flutter before release.

Each response carries an opaque account mutation generation. A change during continuation redacts cached display text and revalidates the loaded window from the newest page; a later page cannot leave a deleted older card in cache. Generation values are compared only for equality.


Under HOME_STEP_PROJECTION, uncomposed and live episodes keep their retained
recordings as compact standalone cards. READY notes are immediately readable;
the app folds only today's pending recording cards into one Processing row
under Listening. Composition replaces those recording cards with the compact
episode card. Preparation remains fenced: GET refuses every partial generation,
so no intermediate chunk can publish both representations. This uses existing
card fields and never adds member IDs or transcript/notes hydration to Home GET.
The preparation control and per-episode progress record the projection policy;
a policy change requires a fully prepared replacement before serving resumes.
Disabling HOME_STEP_PROJECTION restores grouped compact preparation. Pending
collection Delete uses only its displayed recording IDs; full finished episode
Delete still waits for authoritative opened detail membership.
