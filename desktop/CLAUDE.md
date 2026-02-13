# Claude Project Context

## Project Overview
OMI Desktop App for macOS (Swift)

## Logs & Debugging

### Local App Logs
- **App log file**: `/private/tmp/omi.log`

### User Issue Investigation
When debugging issues for a specific user (crashes, errors, behavior), use the **user-logs skill**:
```bash
# Sentry (crashes, errors, breadcrumbs)
./scripts/sentry-logs.sh <email>

# PostHog (events, feature usage, app version)
./scripts/posthog_query.py <email>
```
See `.claude/skills/user-logs/SKILL.md` for full documentation and API queries.

## Related Repositories
- **This repo (`omi-desktop`)** is the current main OMI repo (macOS app + Rust backend)
- **Legacy repo**: `/Users/matthewdi/omi` — old Flutter app + FastAPI Python backend (deprecated)

## Firebase Connection
Use `/firebase` command or see `.claude/skills/firebase/SKILL.md`

Quick connect:
```bash
cd /Users/matthewdi/omi/backend && source venv/bin/activate && python3 -c "
import firebase_admin
from firebase_admin import credentials, firestore, auth
cred = credentials.Certificate('google-credentials.json')
try: firebase_admin.initialize_app(cred)
except ValueError: pass
db = firestore.client()
print('Connected to Firebase: based-hardware')
"
```

## Key Architecture Notes

### Authentication
- Firebase Auth with Apple/Google Sign-In
- Desktop apps should use backend OAuth flow: `/v1/auth/authorize`
- Apple Services ID: `me.omi.web` (shared across all apps)
- iOS apps use native Sign-In, Desktop uses backend OAuth + custom token

### Database Structure
- **Firestore** (`based-hardware`): User data, conversations, action items
- **Redis**: Caching
- **Typesense**: Search

### User Subcollections (Firestore)
- `users/{uid}/conversations` - Has `source` field (omi, desktop, phone, etc.)
- `users/{uid}/action_items` - Tasks (no platform tracking)
- `users/{uid}/fcm_tokens` - Token ID prefix = platform (ios_, android_, macos_)
- `users/{uid}/memories` - Extracted memories

### Platform Detection
- **FCM tokens**: Document ID prefix (e.g., `macos_abc123`)
- **Conversations**: `source` field
- **Action items**: No platform tracking

### Known Limitations
- Firestore has no collection group indexes for `source` field
- Counting users by platform requires iterating all users (slow)
- Apple Sign-In: Only one Services ID per Firebase project

## API Endpoints
- Production: `https://api.omi.me`
- Local: `http://localhost:8080`

## Credentials
See `.claude/settings.json` for connection details.

## Development Workflow

### Building & Running
- **No Xcode project** — this is a Swift Package Manager project
- **Build command**: `xcrun swift build -c debug --package-path Desktop` (the `xcrun` prefix is required to match the SDK version)
- **Full dev run**: `./run.sh` — builds Swift app, starts Rust backend, starts Cloudflare tunnel, launches app
- **Build only**: `./build.sh` — release build without running
- **DO NOT** use bare `swift build` — it will fail with SDK version mismatch
- **DO NOT** use `xcodebuild` — there is no `.xcodeproj`

### After Implementing Changes
- **DO NOT** run the app after making changes
- **DO NOT** run build commands after making changes
- Let the user run `./run.sh` to test the app manually
- Wait for user feedback before making additional changes

## SwiftUI macOS Patterns

### Click-Through Prevention for Sheets/Modals

**CRITICAL**: On macOS, when dismissing sheets or modals, click events can "fall through" to underlying views, causing the cursor to jump and trigger unintended clicks.

**Root cause (FIXED):** The `ClickThroughView.swift` sidebar wrapper was using `NSEvent.addLocalMonitorForEvents` which captured clicks from ALL windows including sheets. When a sheet was dismissed, the captured click location was replayed using `CGEvent.post()` with `mouseCursorPosition`, which actually moves the cursor. The fix was adding a guard to only capture clicks from the sidebar's own window:
```swift
guard event.window == window else { return event }
```

### Dismiss Button Components (AppsPage.swift)

**`SafeDismissButton`** - For native SwiftUI `.sheet()` modals:
```swift
SafeDismissButton(dismiss: dismiss)
```

**`DismissButton`** - For overlay-based modals with external dismiss control:
```swift
DismissButton(action: { showModal = false })
```

Both components:
- Use `@State private var isPressed` to prevent double-taps
- Call `NSApp.keyWindow?.makeFirstResponder(nil)` to consume clicks
- Use async delay before triggering dismiss
- Log with `DISMISS:` or `DISMISS_BUTTON:` prefix

### Click-Outside-to-Dismiss Sheets

Use `DismissableSheetModifier` for modals that should dismiss when clicking outside (defined in `AppsPage.swift`):

```swift
.dismissableSheet(isPresented: $showModal) {
    MyModalContent(onDismiss: { showModal = false })
        .frame(width: 500, height: 650)
}
```

**Key requirements:**
1. Pass an `onDismiss` callback to the modal content
2. Modal content should use `DismissButton(action: onDismiss)` for the close button
3. The modifier adds a dimmed background that dismisses on tap

**Example modal that supports both native sheet and overlay presentation:**
```swift
struct MyModal: View {
    @Environment(\.dismiss) private var environmentDismiss
    var onDismiss: (() -> Void)? = nil  // Optional for overlay presentation

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var body: some View {
        VStack {
            HStack {
                Spacer()
                DismissButton(action: dismissSheet)
            }
            // ... content
        }
    }
}
```

### Sheet-to-Sheet Transitions

When transitioning between sheets, dismiss first, then use delay:
```swift
onCreatePersona: {
    showFirstSheet = false
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
        showSecondSheet = true
    }
}
```

## User Task Completion Reporting

When completing a task that was triggered by an app user request (bug report, feature request, support inquiry, etc.) and you have the user's email address, **send them an email about the results** using the `omi-email` skill:

```bash
node /Users/matthewdi/omi-analytics/scripts/send-email.js \
  --to "<user-email>" \
  --subject "<brief result summary>" \
  --body "<what was done, what they should expect, any next steps>"
```

- Write as Matt (first person "I", not "we") — the user already has an ongoing email thread with us, so treat this as a casual continuation of that conversation, not a fresh introduction
- Be concise and direct — they know the context, just share what was done and any next steps (e.g. "update the app")
- Only send when there are meaningful results to share (don't email for internal-only changes)
