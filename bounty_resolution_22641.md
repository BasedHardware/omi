# Resolution for Issue #22641: fix(backend): normalize naive/aware/ISO timestamps in smart_merge_policy and smart_merge_state

- **Issue URL**: https://github.com/BasedHardware/omi/issues/22641
- **Requirements Checked**:
> ## Summary

`backend/utils/conversations/smart_merge_policy.py` and `backend/utils/conversations/smart_merge_state.py` perform direct `<`, `max()`, `-`, and `.timestamp()` operations on `started_at`, `finished_at`, and `created_at` values from conversation rows and `smart_merge.fragments` ledger ent

- **Payout Wallet (Base USDC)**: `0x1028CB5543e73167E6708f94E08Aff8a640F0164`
