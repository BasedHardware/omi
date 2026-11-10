# Composer thrift fold (L8 + L9)

Date: 2026-11-10
Owner: refactor-lead

L8 has one kill switch, `EPISODE_COMPOSER_THRIFT`: unset means on; explicit
false/0/off/no restores legacy behavior. It covers stable notes/L1 prompt-version
reuse keys, deterministic noise/short-owner L1 admission, notes-based single-member
episodes, keep-paid compose repair/short ledes/superseded-result retention, and
late-open composition. It can go live after normal gates. Notes gain a bounded
12-word gist in the existing call; schema additions remain readable on rollback.

L9 has its own switch, `EPISODE_COMPOSER_NOTES_FIRST`, default OFF. It remains off
until David records a side-by-side verdict; refactor-lead owns the follow-up by
2026-12-10. It changes only the next paid compose's inputs. Turning off L8 leaves
L9 independent, and turning off L9 leaves L8 serving.

Latecompose salvage retains late finalization deferral, first-member fallback
titles, the first-open detail trigger, a read-side grace exit, and bounded Flutter
polling. Dropped repeated late deferral after an episode already has a composed result: the
salvage client cannot distinguish a completed page from a completed page awaiting
replacement, so it would keep showing stale notes. Such arrivals retain normal
finalize scheduling. First composition still waits for open. Its separate kill
switch was folded into L8. L9's separate percent flag
was removed so this fold introduces exactly two flag registry entries. Late-age
and grace duration settings remain numeric tuning, not additional kill switches.

Completed integration gaps: preserve close/read/member_final trigger labels;
clear deferral on deterministic single-member mapping; accept lede-only composed
pages; update details opened outside Home; fence async detail results after owner
change/disposal. No tests are skipped or weakened.

Paid output containing a member removed or hidden during compose is discarded,
so the retention optimization cannot reintroduce hidden content. Excerpt truncation
honors even a remaining budget smaller than its truncation marker. L8 repair also
works for L9 final JSON without resending notes or transcripts.

Known source CI failures: unbounded-label guard violations in L1 and compose
metrics, lifecycle writer inventory drift, and E2E memory fixtures below the new
admission floor. Closed labels and reviewed writer sites fix the guards; substantive
fixture speech keeps the real memory-fence and exactly-once assertions active.
