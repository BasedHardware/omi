# Product analytics integrity (desktop)

Measurement contract for desktop chat and voice telemetry. The component guide
keeps the privacy and product-authority hard rules inline; this file is the
full contract.

- A desktop chat query starts after local concurrency/quota preflight and must
  emit exactly one terminal outcome: `completed`, `failed`, or `cancelled`.
  Intentional Stop and supersession are cancellations, never errors.
- A physical voice shortcut turn emits one start and one terminal outcome from
  the coordinator. Full-answer duration ends at playback drain; a later journal
  failure does not rewrite a delivered response as missing. Intentional and
  too-short endings are excluded from response-failure rates.
- Query latency ends when the final answer is visible. Persistence, title
  generation, and other post-answer work have their own reliability signals and
  must not inflate user-visible query duration.
- Product authority is independent from telemetry. Revoked or timed-out turns
  cannot apply late callbacks/results or persist a late response even if
  analytics is disabled or refactored.
- PostHog receives bounded dimensions and shape metadata only. Never send raw
  prompts, responses, notification/window titles, filesystem paths, or exception
  messages. Keep diagnostic detail in the private local log.
- Production `QueryTracer` output is shape-only and stored under a `0700`
  directory in `0600` files. Full prompt/response/tool content is a deliberate
  non-production debugging capability only.
