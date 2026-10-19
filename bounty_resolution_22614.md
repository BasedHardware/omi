# Resolution for Issue #22614: [Bounty proposal] fix(calendar): normalize naive start timestamps and guard malformed start dicts in multi-window sort ($50 proposed)

- **Issue URL**: https://github.com/BasedHardware/omi/issues/22614
- **Requirements Checked**:
> ### Summary
In `backend/utils/retrieval/tools/calendar_tools.py`, `get_calendar_events_tool()` uses an iterative 30-day window search for past date ranges longer than 30 days (`days_range > 30 and time_max <= datetime.now(timezone.utc)`), collects `events_with_time`, and sorts them via `events_with_

- **Payout Wallet (Base USDC)**: `0x1028CB5543e73167E6708f94E08Aff8a640F0164`
