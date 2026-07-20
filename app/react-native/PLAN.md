# Omi App — RN Screen Plan (mirrors Flutter Omi app)

## Flutter Omi app layout (from user, 2026-07-20)

### Home tab
- Top bar:
  - One side: "record" / "connect Omi device" button
  - Opposite side: settings icon
- Body (scroll):
  - Brief list of items from **Conversations**
  - **Daily Recaps** section
  - **Mind Map** section
- Bottom: rounded input component with a **mic button**, placeholder:
  "omi, anything about your life?"
- Bottom nav tabs: **Home, Conversations, (Memories/Capture = "tass"?), Apps**
  (user listed home / conversations / tass / apps)

### Current RN state (app/react-native)
Tabs in `app/(tabs)/_layout.tsx`: home, capture, conversations, memories, settings
- HomeScreen: lists recent conversations + latest memories (plain Text rows)
- ConversationsScreen: list of conversations
- CaptureScreen: ?
- MemoriesScreen: ?
- SettingsScreen: ?

## Mapping / work needed to match Flutter
1. **HomeScreen** — add:
   - Top bar: record/connect-device button (left) + settings icon (right, links to settings)
   - Daily Recaps section (new store/section)
   - Mind Map section (new)
   - Bottom rounded input + mic button with placeholder "omi, anything about your life?"
2. Keep conversations/memories/capture; verify bottom-nav labels match
   (Home, Conversations, Memories/Capture, Apps). May need an "Apps" tab.
3. Settings icon should navigate to settings tab.
