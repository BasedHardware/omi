**Describe the bug**
The Omi Android app (Beta) crashes immediately upon launch, showing only a loading spinner before closing with the system message "Omi keeps stopping". This completely prevents app usage and has been occurring since mid-May 2025. Prior to the complete crash, the app had issues downloading voice recordings in early April, showing "40+ hours of records need to be saved".

**To Reproduce**
Steps to reproduce the behavior:
1. Install Omi app from Google Play Store (Beta program)
2. Launch the app by tapping the icon
3. Observe loading spinner appears for approximately 1 second
4. App crashes and closes automatically
5. Android system displays "Omi keeps stopping" error message

**Current behavior**
- App shows loading/splash screen with spinner animation
- After ~1 second, app force closes without any user interaction
- Android system error notification appears: "Omi keeps stopping"
- App cannot be used at all - crashes on every launch attempt
- No error message or crash report is displayed to the user
- Granting permissions (Nearby Devices) does not resolve the issue
- Force stopping, clearing cache/data, and reinstalling does not fix the problem

**Expected behavior**
- App should complete initialization and display either:
  - Onboarding screen for new users
  - Home screen for existing users
- App should connect to Omi device via Bluetooth
- Voice recordings should sync properly
- All app features should be accessible

**Screenshots**
Video evidence provided showing the crash behavior (user has video demonstrating the issue)

**user ID (can we access the user info to validate the bug?):**
N/A - Cannot access app to retrieve user ID due to startup crash

**Smartphone + device (please complete the following information):**
 - Device: [User to provide - e.g. Samsung Galaxy S23, Pixel 8]
 - OS: Android [User to provide version - e.g. Android 14]
 - Browser: N/A (native app issue)
 - App Version: Beta version from Play Store (latest as of May 2025)
 - Device version: Omi device firmware [User to provide if known]

**Additional context**
- Issue timeline:
  - Early April 2025: Voice recording sync stopped working ("40+ hours of records need to be saved")
  - Mid-May 2025: Complete app crash on startup began
- Potentially related to OAuth implementation changes merged around May 19, 2025
- App package name: com.friend.ios (despite being Android app)
- Related to issue #2357 regarding integration app loading crashes
- Pull request #2436 submitted with comprehensive fix for initialization error handling
- The crash appears to be caused by unhandled exceptions during app initialization, particularly when Firebase/OAuth configuration is missing or services fail to initialize