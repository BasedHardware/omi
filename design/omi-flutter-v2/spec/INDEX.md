# Screen index

Generated. 58 screens, 519 interactive elements, 205 navigation edges.

| Screen | Title | Plan IDs | Stage | Presented as | Controls | File |
|---|---|---|---|---|---|---|
| `Startup` | Startup failure | L01 | S02 | root (replaces app shell) | 2 | `screens/01-launch-onboarding.md` |
| `Gate` | Update / migration gate | L02 | S02 | root (blocking) | 2 | `screens/01-launch-onboarding.md` |
| `Welcome` | Welcome | L03 | S02 | root of the onboarding stack | 2 | `screens/01-launch-onboarding.md` |
| `SignIn` | Sign in | O01 | S02 | push (onboarding stack) | 5 | `screens/01-launch-onboarding.md` |
| `Consent` | Data and AI consent | O02 | S02 | push (onboarding stack) | 3 | `screens/01-launch-onboarding.md` |
| `Name` | Name | O03 | S02 | push (onboarding stack) | 4 | `screens/01-launch-onboarding.md` |
| `Language` | Primary language | O04 | S02 | push (onboarding stack) | 12 | `screens/01-launch-onboarding.md` |
| `Source` | How did you hear about Omi | O05 | S02 | push (onboarding stack) | 14 | `screens/01-launch-onboarding.md` |
| `Permissions` | Permissions | O06 | S02 | push (onboarding stack) | 19 | `screens/01-launch-onboarding.md` |
| `Voice` | Teach Omi your voice | O07 | S06 | push (onboarding stack) | 9 | `screens/01-launch-onboarding.md` |
| `VoiceReview` | Review your answers | O07 | S06 | push (onboarding stack) | 8 | `screens/01-launch-onboarding.md` |
| `Knows` | What Omi knows | O08 | S09 | push (onboarding stack) | 2 | `screens/01-launch-onboarding.md` |
| `OnboardPlan` | Choose a plan (new) | M51 (onboarding placement) | S12 (placeholder in S02) | push (onboarding stack) | 10 | `screens/01-launch-onboarding.md` |
| `Complete` | Onboarding complete | O09 | S12 | push, then replace root with Home | 1 | `screens/01-launch-onboarding.md` |
| `TutorialIntro` | Device tutorial intro | T01 | S04 | full-screen cover (tutorial stack) | 2 | `screens/02-device-tutorial-sync.md` |
| `TutorialTranscribe` | Tutorial: live transcription | T02 | S06 | push (tutorial stack) | 3 | `screens/02-device-tutorial-sync.md` |
| `TutorialAsk` | Tutorial: press to ask | T03 | S10 | push (tutorial stack) | 4 | `screens/02-device-tutorial-sync.md` |
| `TutorialPower` | Tutorial: power off and on | T04 | S04 | push (tutorial stack) | 4 | `screens/02-device-tutorial-sync.md` |
| `TutorialDoubleTap` | Tutorial: double-press | T05 | S12 | push (tutorial stack) | 5 | `screens/02-device-tutorial-sync.md` |
| `Pairing` | Connect Omi | D01 | S04 | sheet (large) over Home | 4 | `screens/02-device-tutorial-sync.md` |
| `Discover` | Nearby devices | D02 | S04 | push inside the pairing sheet | 8 | `screens/02-device-tutorial-sync.md` |
| `Device` | Device settings | D03 | S04 (metadata) / S12 (settings) | sheet (large) from Home status pill | 16 | `screens/02-device-tutorial-sync.md` |
| `Firmware` | Firmware update | D05 | S12 | push (device sheet stack) | 3 | `screens/02-device-tutorial-sync.md` |
| `Sync` | Offline recordings | Y01 | S05 | push (from Home sync card, Device, Settings, Conversations) | 10 | `screens/02-device-tutorial-sync.md` |
| `FirstDay` | Home, first day | C01 | S03 | tab root (Home) — empty state of Main | 6 | `screens/03-home-capture-conversations.md` |
| `Main` | Home (Today) | C01 | S03 | tab root (Home) | 23 | `screens/03-home-capture-conversations.md` |
| `Live` | Live capture | C04 | S06 | full-screen cover (from Home Live card) | 7 | `screens/03-home-capture-conversations.md` |
| `Processing` | Processing | C05 | S05 | full-screen cover (after Finish) | 2 | `screens/03-home-capture-conversations.md` |
| `Conversation` | Conversation | C03 | S03 (read) / S07 (actions) | push | 30 | `screens/03-home-capture-conversations.md` |
| `Speaker` | Tag a speaker | M20 | S07 | sheet (medium → large) | 8 | `screens/03-home-capture-conversations.md` |
| `Conversations` | Conversations | C02 | S03 (read) / S07 (actions) | tab root (Conversations) | 27 | `screens/03-home-capture-conversations.md` |
| `ContextMenu` | Long-press menu | M17 | S07 | context menu (system `contextMenu` with preview) | 11 | `screens/03-home-capture-conversations.md` |
| `Offline` | Conversations offline | C02 | S03 | state of the Conversations tab | 9 | `screens/03-home-capture-conversations.md` |
| `Search` | Search everything | C02 · C10 · C12 | S03 | push (field focused) from Home | 13 | `screens/03-home-capture-conversations.md` |
| `Recap` | Daily recap | C08 | S09 | push | 10 | `screens/03-home-capture-conversations.md` |
| `ShareCard` | Share recap card | C08 | S07 | sheet (large) | 6 | `screens/03-home-capture-conversations.md` |
| `Tasks` | Tasks and goals | C12 | S08 | tab root (Tasks) | 15 | `screens/04-tasks-chat-memories.md` |
| `TaskEdit` | Edit task | M34 | S08 | sheet (large) | 11 | `screens/04-tasks-chat-memories.md` |
| `Chat` | Ask Omi | C09 · M38 · M39 | S10 | push (from the Ask button on any tab, or scoped from a conversation) | 20 | `screens/04-tasks-chat-memories.md` |
| `VoiceAsk` | Voice mode | C09 | S10 | full-screen cover | 3 | `screens/04-tasks-chat-memories.md` |
| `Memories` | Memories | C10 | S09 | push (from Home memories card, Settings) | 11 | `screens/04-tasks-chat-memories.md` |
| `MemoryDetail` | Memory | M32 | S09 | push (existing) / sheet (new) | 8 | `screens/04-tasks-chat-memories.md` |
| `Graph` | Memory graph | C11 | S09 | push | 11 | `screens/04-tasks-chat-memories.md` |
| `Apps` | Apps | A01 | S11 | tab root (Apps) | 21 | `screens/05-apps-calls-settings.md` |
| `AppDetail` | App detail and setup | A04 | S11 | push | 6 | `screens/05-apps-calls-settings.md` |
| `Integrations` | Integrations | I01 | S11 | push (from Settings, Tasks) | 8 | `screens/05-apps-calls-settings.md` |
| `Call` | Active call | P05 | S12 | full-screen cover (CallKit in-call UI when locked) | 5 | `screens/05-apps-calls-settings.md` |
| `Settings` | Settings | M01 | S12 | sheet (large) from Home's Account button | 23 | `screens/05-apps-calls-settings.md` |
| `Appearance` | Appearance | (new) | S01 | push (settings stack) | 10 | `screens/05-apps-calls-settings.md` |
| `Plan` | Plan and usage | S16 | S12 | push (settings stack) | 10 | `screens/05-apps-calls-settings.md` |
| `Upgrade` | Plans | M51 | S12 | sheet (large) | 9 | `screens/05-apps-calls-settings.md` |
| `Privacy` | Data and privacy | S19 | S12 | push (settings stack) | 9 | `screens/05-apps-calls-settings.md` |
| `People` | People | S15 | S09 | push (settings stack) | 5 | `screens/05-apps-calls-settings.md` |
| `Notifications` | Notifications | S13 | S12 | push (settings stack) | 8 | `screens/05-apps-calls-settings.md` |
| `Transcription` | Transcription | S08 | S06 | push (settings stack) | 8 | `screens/05-apps-calls-settings.md` |
| `DeleteAccount` | Delete account | S24 | S12 | push (settings stack) | 6 | `screens/05-apps-calls-settings.md` |
| `LockScreen` | Lock Screen Live Activity | (proposed) | S13 | ActivityKit Live Activity | 5 | `screens/06-system-surfaces.md` |
| `HomeScreen` | Home Screen widgets and Dynamic Island | (proposed) | S13 | WidgetKit + Live Activity | 3 | `screens/06-system-surfaces.md` |
