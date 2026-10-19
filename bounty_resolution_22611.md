# Resolution for Issue #22611: [Bounty proposal] fix(memory): normalize mixed naive and aware evidence timestamps when ordering capture devices ($50 proposed)

- **Issue URL**: https://github.com/BasedHardware/omi/issues/22611
- **Requirements Checked**:
> ### Summary
In `backend/utils/memory/canonical_memory_adapter.py`, `_ordered_capture_devices_from_evidence()` builds sort keys `(0, created_at)` from evidence entries where `created_at` may be a `datetime` object or an ISO-8601 string, and then sorts them via `keyed.sort(key=lambda item: item[0])`.


- **Payout Wallet (Base USDC)**: `0x1028CB5543e73167E6708f94E08Aff8a640F0164`
