**Describe the bug**
The Omi app displays "40+ hours of records need to be saved" but voice recordings are not syncing to the backend. The sync functionality is hidden unless users have 2+ minutes of recordings, causing many users to accumulate large backlogs without knowing they need to sync. When sync is attempted, failures occur silently without user notification.

**To Reproduce**
Steps to reproduce the behavior:
1. Use Omi device to record audio throughout the day
2. Open the Omi app
3. Notice no sync icon appears if total recordings < 2 minutes
4. Continue using device until recordings accumulate to hours/days
5. Eventually see "40+ hours of records need to be saved" message
6. If sync icon appears (download icon in app bar), tap it
7. Tap "Sync All" - may fail silently without error messages

**Current behavior**
- Sync icon only visible when recordings exceed 2 minutes (120 seconds)
- No persistent sync option in settings/menu
- Sync failures are silent - no error messages shown to users
- No automatic retry for failed syncs
- Files marked "corrupted" are never retried
- No progress indication or status updates during sync
- Network errors don't trigger automatic retry when connection restored

**Expected behavior**
- Sync option should always be accessible (lower threshold or permanent menu item)
- Clear error messages when sync fails (network, auth, server errors)
- Automatic retry for temporary failures
- Progress indication showing which files are syncing
- Ability to retry individual failed files
- Background sync when connection is restored
- Proper handling of authentication token expiry

**Screenshots**
N/A - Issue occurs in background sync process. Sync icon may not even be visible to users.

**user ID (can we access the user info to validate the bug?):**
Cannot access due to startup crash from issue #2437

**Smartphone + device (please complete the following information):**
 - Device: All Android devices
 - OS: All Android versions  
 - Browser: N/A
 - App Version: Beta (current Play Store version)
 - Device version: All Omi device firmware versions

**Additional context**
This appears to be an unreported but critical issue affecting the core functionality of recording and saving voice data. Investigation revealed:

- High threshold (2 minutes) prevents users from seeing sync option
- Silent error handling leaves users unaware of sync failures  
- No retry mechanism means failed uploads are lost
- WAL (Write-Ahead Log) system stores recordings locally but sync issues prevent upload
- Related to PR #2436 which fixes the app crash, but this sync issue is separate

The "40+ hours" represents approximately 144,000 seconds of audio data stuck in local storage. This is a critical data loss scenario as users believe their recordings are being saved but they're actually accumulating locally without successful upload to the backend.