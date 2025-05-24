# Fix: Lower sync threshold to prevent voice recording backlog

## Summary
This PR addresses the critical issue where users accumulate "40+ hours of records need to be saved" because the sync functionality is hidden until they have 2+ minutes of recordings. By lowering the threshold to 30 seconds, users can sync more frequently and avoid large backlogs.

## Problem
Users are experiencing a silent data accumulation issue:
- Sync icon only appears after 120 seconds (2 minutes) of recordings
- Many users never see the sync option
- Recordings accumulate locally without being uploaded
- Users report "40+ hours" of unsynced data
- No error messages when sync fails

## Solution
This PR implements a simple but effective fix:
- **Lowered sync threshold from 120 to 30 seconds**
- Makes sync option visible much earlier
- Encourages frequent syncing
- Prevents large backlog accumulation

## Changes Made
- `app/lib/pages/home/page.dart`: Changed threshold from 120 to 30 seconds
- `app/lib/pages/conversations/widgets/local_sync.dart`: Updated matching threshold

## Testing
- Tested with recordings under 30 seconds - sync icon doesn't appear
- Tested with recordings over 30 seconds - sync icon appears correctly
- Verified sync functionality works as expected
- No regression in existing functionality

## Impact
- **Immediate visibility** of sync option for users with minimal recordings
- **Prevents data accumulation** by encouraging frequent syncs
- **Better user experience** - users aware they need to sync
- **Reduces support burden** - fewer "lost recordings" complaints

## Related Issues
- Fixes unreported issue: "40+ hours of records need to be saved"
- Works in conjunction with PR #2436 (app crash fix)
- Addresses core functionality of voice recording storage

## Future Improvements
While this PR provides immediate relief, future enhancements could include:
1. Permanent sync option in settings menu
2. Better error handling with user notifications
3. Automatic retry for failed syncs
4. Background sync when app is closed
5. Progress indicators during sync

## Checklist
- [x] Code follows project style
- [x] Self-review completed
- [x] Tested threshold changes
- [x] No breaking changes
- [x] Improves user experience