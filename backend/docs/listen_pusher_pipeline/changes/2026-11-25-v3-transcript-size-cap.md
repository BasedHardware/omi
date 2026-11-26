# v3 transcript size cap (SCA-2918)

Derived v3 windows split at a deterministic line boundary when the estimated
inline transcript reaches 900 KiB. The estimate budgets JSON and enhanced
encryption expansion without counting on compression savings. The next
reconcile replans a rejected unpublished window using the existing continuation
and claim rules. Existing locked windows keep their custody.

Set `CONVERSATIONS_V3_TRANSCRIPT_SIZE_CAP=off` to disable new size cuts.
Count `event=v3_transcript_size_cap_split` in builder logs. Verify that
backend-sync reports zero `is longer than 1048487 bytes` errors and corrected
reconcile 5xx returns to baseline.
