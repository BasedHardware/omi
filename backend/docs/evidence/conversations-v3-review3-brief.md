# Scope: conversations v3 final review round

Read-only scope at 05dd8844950, BasedHardware/omi, lane/conversations-v3.
Inspect only the isolated panel checkout and Git objects; never read another
worktree or any upstream-keep-clean/ directory. No production/private data,
paid Omi model calls, writes, push/PR/merge/rebase/deploy or config changes.
Primary owns implementation. Keep the investigation bounded to these seams:
1. Compact /live row must include finished_at key (nullable) and match app
Conversation required keys. Audio /urls pending must return nonempty pending
alias entries without URLs; honor unavailable marker; playback_start for skew;
readiness must not permanently cache partial audio; plugin backup retry signal.
2. Pending32-page anchor must include continuous open recording chain beyond
20min and preserve chronology with late earlier audio. Process/purge sweeps need
cursor pages and per-row error handling. Undecodable recording must settle as
unreadable. On-open reconcile errors should use stored row; timeout must retain
builder lease until paid worker exits. Renewals need bounded lifetime/retries.
Global multiple-open check must precede all transaction batches. Failure metric.
3. Summary prepare/stream early-return lease release. Replace 192 composite count
indexes with unfiltered layer aggregates + bounded filtered scan. Episode MEMBER_FIELDS
needs recording/home_hidden. Verify episode client marker remains beta-only.
PR rollout/deletion must explicitly name V3-BACKFILL-30D-PARTITIONS.
Return concrete confirmed risks and narrow implementation/test suggestions.
Existing round2 manual intent/failed tiles/recognition fallback must survive.
No app UI changes, no Q12 prompt or sync merge rewrites. Synthetic tests only.
