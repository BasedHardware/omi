# Resolution for Issue #22638: [Bounty proposal] fix(conversations): normalize mixed naive, aware, and ISO timestamps in find_neighbor ($50 proposed)

- **Issue URL**: https://github.com/BasedHardware/omi/issues/22638
- **Requirements Checked**:
> ### Summary
`find_neighbor` in `backend/utils/conversations/relevance.py` compares and subtracts `started_at` and `finished_at` against candidate conversation rows (`other_end <= started_at`, `(started_at - other_end).total_seconds()`, `other_start >= finished_at`, `(other_start - finished_at).total

- **Payout Wallet (Base USDC)**: `0x1028CB5543e73167E6708f94E08Aff8a640F0164`
