# Composer stack review dispositions

Date: 2026-11-10
Owner: refactor-lead

The reviewed fold #25065 is split with normal merges: L8a reuse → L8b thrift → L9 notes-first. Each PR targets main and names its predecessor. Existing branch history is preserved. No source PR is closed or merged by this work.

L8a `EPISODE_COMPOSER_REUSE` is independently default on. Compatible successful pre-deploy and stable keys survive deploy and flag rollback. Exact inputs, content revision, output validation and routing still invalidate appropriately. No backfill or forced gist regeneration. The additive gist remains in the existing notes call; it is a schema capability rather than a separately gated call.

L8b `EPISODE_COMPOSER_THRIFT` is default on: keep paid output pending while members process, one output-only repair, short readable ledes, deterministic single-member notes and late composition on open. Single-member evidence includes the complete notes, cited segment identity/timing, and recorded span. A title alone does not qualify. Pending paid results wait for settling rather than an immediate paid retry. Removed/hidden members still invalidate paid output.

Late-age uses the episode's recorded start (48 hours), not upload time or individual member age. New members of a composed closed episode re-arm it at attach even if finalization is memoized, preserving #25053's user guarantee. Existing paid notes remain readable while `compose_deferred` is true. A durable opened-deferral epoch keeps a member completing after the client poll from being stranded behind the unopened seven-day hold; completion clears it and a new deferral resets it. Member-final and close defer; first detail open or the seven-day read-side grace exit refreshes the member set. A failed deferral stamp falls through to normal scheduling. Turning thrift off stops read-trigger scheduling and drains durable deferrals through normal recovery.

The client changes only detail refresh and lede-only completion: one read per closed page open, coalesced across concurrent opens; only the server's explicit deferral signal permits at most eight further five-second polls. Each read has a four-second timeout and the sequence has a 45-second deadline. Page exit/account change/disposal cancel publication and further reads. Detail cache never replaces Home's filtered membership. #25022 lands second and must carry this small refresh contract into its redesigned page/provider.

The lease is sized for every permitted paid turn (two 90-second provider attempts plus retry headroom each), with final-write margin. No turn starts without enough deadline headroom. Ownership tokens fence release and final writes, including same-evidence successors. L9 extends the same bound for five turns plus one repair. Per-reply reported input/output tokens include terminal parse/repair failures; logical calls, repairs and failures are labeled. Hidden SDK retry-attempt billing remains a usage-ledger follow-up; these counters alone do not establish variable margin. Deploy dashboards must aggregate the added trigger label and compare full/notes-first cumulative usage. The production metric inventory is a measured snapshot, not fabricated here; refresh it after these metrics serve.

L9 is a separate default-OFF PR until David's side-by-side verdict. Its rollout requires cumulative billed input/output and logical calls per completed compose versus full mode on the same episodes, including failures and provider retries. It does not promise savings merely from an excerpt-byte cap.

Salvage: retained late deferral, first-member fallback, first-open composition, grace recovery and bounded client refresh. Restored composed-episode re-deferral with an explicit client signal. Dropped the separate late-compose flag (folded into thrift), and the notes-first percentage flag (one independent default-off switch). No incomplete salvage behavior remains.
