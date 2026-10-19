# Resolution for Issue #22636: [Bounty proposal] fix(calendar): normalize naive dateTime strings and guard None values in parse_event_times ($50 proposed)

- **Issue URL**: https://github.com/BasedHardware/omi/issues/22636
- **Requirements Checked**:
> ### Summary
`parse_event_times(event)` in `backend/utils/conversations/calendar_utils.py` parses `start['dateTime']` and `end['dateTime']` via `datetime.fromisoformat(str(start['dateTime']).replace('Z', '+00:00'))` without normalizing timezone-naive datetimes to UTC, while all-day `date` events are 

- **Payout Wallet (Base USDC)**: `0x1028CB5543e73167E6708f94E08Aff8a640F0164`
