# V3 Finish before the first derived window

An empty-body Finish can arrive after Listen closes the capture and before its
first derived window exists. An eligible request with no live window can finish
one recent unclaimed Listen recording. The transaction rechecks the full two-hour
live window horizon and refuses a cut when either lookup reaches its cap.
Payloads with fields keep the existing window lookup. The cut uses the existing v3
reconcile path. Whole native batch completion consumes the intent for both single-
and multi-unit records. Terminal silence resolves the intent without cutting unrelated speech.
The terminal-empty HTTP acknowledgement sets `discarded` when no earlier
window member holds speech, so the app can show its existing too-short-or-empty
notice. It does not discard the stored row. While native units are pending,
Finish checks the archived audio bounds independently of projected speech.
A wholly silent recording-scoped Finish also writes a revision-bound receipt
in the completion transaction. The existing include-discarded conversation
list projects that receipt as discarded under the original recording ID, so
the app stops polling and shows the same notice.
If the recording has merged into another row, completion clears the donor's intent
and counts it as redirected. A redirect does not prove the cut is safe for the
survivor's later speech.

The Finish counter records the API kill-switch and owner eligibility exits.
API outcomes (including a capped live-window lookup), committed whole-record
resolution, and first derived settlement have separate outcomes.
See the [v3 pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).
