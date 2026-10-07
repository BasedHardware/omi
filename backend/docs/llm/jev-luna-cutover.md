# Company-paid JEV and Luna cutover

Company-paid Gemini **text and vision generation** is retired. This includes
installed desktop clients that still send Flash, Flash Lite, Pro, or 3.8 Flash
model aliases. Explicit user-paid Gemini BYOK remains supported. Audio/realtime,
TTS, and embeddings retain their separate provider contracts; changing an
embedding model requires a vector migration.

## Serving contract

- Backend feature generation goes through its `omi:auto:*` gateway lane after
  BYOK selection. Former Gemini utilities and wrapped analysis use `gpt-6-luna`.
- Desktop generation uses `omi:auto:desktop-luna`. The BFF translates existing
  Gemini JSON, images, function calls, and streams to OpenAI chat completions
  and translates responses back. Legacy wire aliases remain accepted so this
  backend release also cuts over previously installed clients.
- Legacy `omi:auto:desktop-vertex-*` gateway lane IDs now resolve to Luna too.
  Neither reservation state nor an overflow pin can select Gemini generation.
  Paid gateway routes reject Gemini primary, fallback, and last-known-good
  generation providers at configuration load.
- New macOS and Windows paid screen-task clients use the existing JEV OCR gate
  followed by bounded, single-call Luna extraction. Server admission and its
  lease, auth/plan/quota checks, privacy exclusions, original-user binding, and
  canonical task delivery remain authoritative. `SCREEN_TASK_STOP=1` disables
  the new screen-task path. A JEV provider outage admits Luna extraction;
  auth, plan, quota, and stop denials remain terminal.
- Gateway failures return unavailable. There is no paid Gemini fallback.
  User-paid BYOK uses its own credentials and never spills into paid generation.
  Screen-frame approvals retain the signed managed-policy model contract;
  explicit BYOK inference attribution comes from the provider usage ledger.

## Deployment order

1. Deploy the gateway image/config first and verify the new
   `omi:auto:desktop-luna` and former Gemini feature lanes serve Luna, with
   explicit reasoning options and no Gemini generation fallback. Verify normal
   ILB/VPC reachability using the existing gateway serving probe.
2. Deploy this backend image to every generation host: backend Cloud Run,
   backend-listen, sync/backfill, separately released desktop-backend, and
   jobs that import `get_llm`. Verify service authentication and gateway URL
   configuration on each host. Publish the desktop clients after the BFF.
3. Observe gateway provider/model usage and unavailable/error rates, JEV gate
   acceptance/fail-open rates, screen-task candidate delivery, and BYOK funding
   attribution. Legacy desktop wire model names are request aliases; the
   gateway's served model identifies actual paid usage.

The new desktop lane deliberately fails closed against an older gateway.
Deploying the backend first therefore causes an availability gap rather than
paid Gemini traffic. Reverting the gateway or backend image to a pre-cutover
version restores that older version's Gemini behavior and violates the cutoff;
repair the Luna route or pause generation instead.

This code does not modify the GCP reservation. The existing commitment remains
billable until the separately managed reservation change takes effect, even
when Gemini text-generation utilization drops to zero. Provision enough Luna
quota and gateway capacity for the migrated traffic during that overlap.

## Verification boundaries

Hermetic tests cover routing, request/response translation, rejected paid
Gemini configuration, BYOK exemptions, screen-task gating, and client delivery.
They do not establish live Luna quota, provider latency/quality, Windows native
runtime behavior, or the reservation's billing transition. Those checks belong
to deployment and the reservation operation.
