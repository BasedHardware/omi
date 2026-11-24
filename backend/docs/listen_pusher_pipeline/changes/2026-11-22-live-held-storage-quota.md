# Listen handles held-storage quota refusal during shutdown

SCA-3646. Listen classifies a rejected monthly held-storage reservation and
counts the first refusal per session. Provider drain and raw-archive close
continue after the rejection. Pending PCM keeps its bounded final retry, and
the held receipt reports only published audio.

This applies with or without fragment writes. The
[held-audio runbook](../../runbooks/cap-hold-durability.md#monthly-live-held-storage-quota)
defines the custody outcome and the production readback.
