# Explicit manual finishes on v3 Home

SCA-3024 keeps the derived row at the explicit cut eligible for Home even when
classified as media or wearer-recognized background. When the cut has multiple
derived rows, the final fragment owns the override because it contains the last
line of the manually ended window. The existing source marker reconstructs the
cut and a retained row keeps its stored manual-end marker. Classification and
the existing Home deletion and discard filters are preserved.

The [v3 runtime contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
documents the default-on kill switch. For a rollout window, divide the increase
in `omi_conversations_v3_manual_end_home_total{visibility="visible"}` by the
increase across both visibility labels, summed across builders. This measures
successful first processing settlements after the backend Home visibility checks.
It excludes historical runs, deleted rows, discarded rows and failed summaries.
Serving verification must also reconcile the eligible count against the Home list
and report user exceptions, failed summaries and unknown outcomes separately.
