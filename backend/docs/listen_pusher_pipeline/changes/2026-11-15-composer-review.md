# Episode context and notes review follow-up

The composer layers a stricter filter over chat's shared eligibility predicate: explicit unknown/third-party subjects and non-fact kinds are excluded, including legacy rows. Loader tests exercise mixed canonical and legacy rows through both list and vector paths, and recheck untrusted search adapter results.

Chat still admits visible noncanonical legacy rows without checking their kind or subject at `backend/models/knowledge_ledger_policy.py:121`; its legacy prompt renderer consumes them at `backend/utils/llms/memory.py:74`. This change leaves that chat behavior untouched so the chat owner can assess and address the gap separately.

Notes use prompt version notes-4 with a pinned source digest (including the scaling configuration). A deploy schedules zero regenerations: dedupe is consulted only inside an already requested processing attempt. Exact short and switch-off notes-3 checkpoints with identical routing/dependencies/inputs are accepted and restamped without an LLM call; only eligible scaled packets add a scaled-detail discriminator, so old long output is recomputed once when independently reprocessed.
