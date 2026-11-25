# V3 Finish before the first derived window

An empty-body Finish can arrive after Listen closes the capture and before its
first derived window exists. An eligible request with no live window can finish
one recent unclaimed Listen recording. The transaction rechecks the full two-hour
live window horizon and refuses a cut when either lookup reaches its cap.
Payloads with fields keep the existing window lookup. The cut uses the existing v3
reconcile path. Whole native batch completion consumes the intent for both single-
and multi-unit records. Terminal silence resolves the intent without cutting unrelated speech.

The Finish counter records the API kill-switch and owner eligibility exits.
API outcomes, committed whole-record consumption or silence, and first derived
settlement have separate outcomes.
See the [v3 pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).
