# Navigation graph

Generated from every link in the designs. `Transition` uses the vocabulary in `spec/README.md`. Same-screen links (prototype placeholders) are omitted; their production behaviour is in the screen files.

| From | Control | To | Transition |
|---|---|---|---|
| `AppDetail` | Back | `Apps` | pop |
| `Appearance` | Back | `Settings` | pop |
| `Apps` | (icon) | `AppDetail` | push |
| `Apps` | Ask Omi | `Chat` | push |
| `Apps` | Conversations | `Conversations` | push |
| `Apps` | Home | `Main` | push |
| `Apps` | Set Up | `AppDetail` | push |
| `Apps` | Tasks | `Tasks` | push |
| `Call` | End call | `Main` | push |
| `Call` | Minimize | `Main` | uncover |
| `Chat` | Back | `Main` | pop |
| `Chat` | Find chat apps | `Apps` | push |
| `Chat` | Voice mode | `VoiceAsk` | cover |
| `Chat` | ‹dynamic› | `Conversation` | push |
| `Complete` | Start Using Omi | `Main` | push |
| `Consent` | Agree and Continue | `Name` | push |
| `Consent` | Use a Different Account | `SignIn` | push |
| `ContextMenu` | 2:42 PM App UX and battery concerns The UX feels inconsist… | `Conversation` | push |
| `ContextMenu` | 2:43 PM App reliability and subscription concerns Paying u… | `Conversation` | push |
| `ContextMenu` | 3:14 PM Call Chitapa reminder A note to yourself to call C… | `Conversation` | push |
| `ContextMenu` | Copy Summary | `Conversations` | in place |
| `ContextMenu` | Delete | `Conversations` | in place |
| `ContextMenu` | Dismiss | `Conversations` | in place |
| `ContextMenu` | Merge With… | `Conversations` | in place |
| `ContextMenu` | Move to Folder | `Conversations` | in place |
| `ContextMenu` | Share | `Conversations` | in place |
| `ContextMenu` | Star | `Conversations` | in place |
| `Conversation` | Ask about this conversation | `Chat` | push |
| `Conversation` | Back | `Main` | pop |
| `Conversation` | Check whether the battery-drain reports are valid No date … | `TaskEdit` | sheet |
| `Conversation` | Who is Speaker 2? Tag them once and Omi recognizes their v… | `Speaker` | sheet |
| `Conversations` | 11:40 AM iPhone roadmap Order of work for the native app: … | `Conversation` | push |
| `Conversations` | 2:42 PM App UX and battery concerns The UX feels inconsist… | `Conversation` | push |
| `Conversations` | 2:43 PM App reliability and subscription concerns Paying u… | `Conversation` | push |
| `Conversations` | 3:14 PM Call Chitapa reminder A note to yourself to call C… | `Conversation` | push |
| `Conversations` | 6:05 PM Pricing review Annual plan framing and what the fr… | `Conversation` | push |
| `Conversations` | Apps | `Apps` | push |
| `Conversations` | Ask Omi | `Chat` | push |
| `Conversations` | Home | `Main` | push |
| `Conversations` | Offline recordings | `Sync` | push |
| `Conversations` | Tasks | `Tasks` | push |
| `DeleteAccount` | Back | `Privacy` | pop |
| `DeleteAccount` | Export your data first | `Privacy` | push |
| `DeleteAccount` | Keep My Account | `Privacy` | push |
| `Device` | Close | `Main` | dismiss |
| `Device` | Firmware Update available | `Firmware` | sheet |
| `Device` | Learn how to use Omi | `TutorialIntro` | sheet |
| `Device` | Offline recordings 12 min | `Sync` | push |
| `Discover` | Close | `Main` | dismiss |
| `Discover` | Omi (Maya’s) Nearby · signal weak Connect | `Pairing` | sheet |
| `Discover` | Omi Nearby · signal strong · 42% Connect | `Pairing` | sheet |
| `Discover` | Use iPhone microphone No device needed | `Main` | push |
| `Firmware` | Close | `Device` | dismiss |
| `Firmware` | Done | `Device` | sheet |
| `FirstDay` | Account and settings | `Settings` | sheet |
| `FirstDay` | Apps | `Apps` | push |
| `FirstDay` | Ask Omi | `Chat` | push |
| `FirstDay` | Conversations | `Conversations` | push |
| `FirstDay` | Home | `Main` | push |
| `FirstDay` | Tasks | `Tasks` | push |
| `Graph` | Back | `Memories` | pop |
| `Integrations` | Back | `Settings` | pop |
| `Integrations` | Create your own integration | `Apps` | push |
| `Knows` | Back | `VoiceReview` | pop |
| `Knows` | Continue | `OnboardPlan` | push |
| `Language` | Back | `Name` | pop |
| `Language` | Continue | `Source` | push |
| `Live` | Finish | `Processing` | cover |
| `Live` | Minimize | `Main` | uncover |
| `Main` | 2:42 PM App UX and battery concerns The UX feels inconsist… | `Conversation` | push |
| `Main` | 2:43 PM App reliability and subscription concerns Paying u… | `Conversation` | push |
| `Main` | 3 new memories Subscriptions, battery life, Chitapa | `Memories` | push |
| `Main` | 3:14 PM Call Chitapa reminder A note to yourself to call C… | `Conversation` | push |
| `Main` | Account and settings | `Settings` | sheet |
| `Main` | All Tasks | `Tasks` | push |
| `Main` | Apps | `Apps` | push |
| `Main` | Ask Omi | `Chat` | push |
| `Main` | Call Chitapa Today, 5:00 PM | `Tasks` | push |
| `Main` | Check whether the battery-drain reports are valid From App… | `Tasks` | push |
| `Main` | Conversations | `Conversations` | push |
| `Main` | Daily recap · Wednesday A planning day: pricing, the iPhon… | `Recap` | push |
| `Main` | End conversation | `Processing` | cover |
| `Main` | Omi pendant, 42 percent, charging | `Device` | sheet |
| `Main` | Search | `Search` | push |
| `Main` | See All | `Conversations` | push |
| `Main` | Tasks | `Tasks` | push |
| `Main` | ‹dynamic› ~12 min recorded on the pendant while your phone… | `Sync` | push |
| `Main` | ‹dynamic› …a quick update on the battery-drain reports. Ar… | `Live` | cover |
| `Memories` | Back | `Main` | pop |
| `Memories` | New memory | `MemoryDetail` | push |
| `Memories` | You Omi app Subscriptions Battery Chitapa Pricing Expand | `Graph` | push |
| `Memories` | ‹dynamic› · ‹dynamic› | `MemoryDetail` | push |
| `MemoryDetail` | App UX and battery concerns Today at 2:42 PM · recorded on… | `Conversation` | push |
| `MemoryDetail` | Cancel | `Memories` | dismiss |
| `MemoryDetail` | Save | `Memories` | push |
| `Name` | Back | `Consent` | pop |
| `Name` | Continue | `Language` | push |
| `Notifications` | Back | `Settings` | pop |
| `Offline` | 2:42 PM App UX and battery concerns The UX feels inconsist… | `Conversation` | push |
| `Offline` | 2:43 PM App reliability and subscription concerns Paying u… | `Conversation` | push |
| `Offline` | 3:14 PM Call Chitapa reminder A note to yourself to call C… | `Conversation` | push |
| `Offline` | Apps | `Apps` | push |
| `Offline` | Ask Omi | `Chat` | push |
| `Offline` | Conversations | `Conversations` | in place |
| `Offline` | Home | `Main` | push |
| `Offline` | Offline recordings | `Sync` | push |
| `Offline` | Tasks | `Tasks` | push |
| `OnboardPlan` | Back | `Knows` | pop |
| `OnboardPlan` | Privacy | `Consent` | push |
| `OnboardPlan` | Terms | `Consent` | push |
| `OnboardPlan` | ‹dynamic› | `Complete` | push |
| `Pairing` | Close | `Main` | dismiss |
| `Pairing` | Done | `Main` | push |
| `Pairing` | Not your pendant? See all devices | `Discover` | sheet |
| `People` | Back | `Settings` | pop |
| `Permissions` | Back | `Source` | pop |
| `Permissions` | Continue | `Voice` | push |
| `Plan` | Back | `Settings` | pop |
| `Plan` | See Plans | `Upgrade` | sheet |
| `Plan` | Use on-device transcription Unlimited and private, slightl… | `Transcription` | push |
| `Privacy` | Back | `Settings` | pop |
| `Privacy` | Conversation Coach Transcripts · when you chat with it | `AppDetail` | push |
| `Privacy` | Delete Account | `DeleteAccount` | push |
| `Privacy` | Google Drive Transcripts and summaries · when a conversati… | `AppDetail` | push |
| `Privacy` | Training data program Off | `Upgrade` | sheet |
| `Processing` | Close | `Main` | uncover |
| `Processing` | Work · Today 2:42 PM App UX and battery concerns The UX fe… | `Conversation` | push |
| `Recap` | Back | `Main` | pop |
| `Recap` | Build the iPhone app natively, starting with capture. | `Conversation` | push |
| `Recap` | Hiring Two strong candidates for the iOS role; next step i… | `Conversation` | push |
| `Recap` | Keep a free tier with on-device transcription. | `Conversation` | push |
| `Recap` | Most battery complaints come from one firmware version. | `Conversation` | push |
| `Recap` | Pricing Leaning toward an annual plan with a generous free… | `Conversation` | push |
| `Recap` | Share recap | `ShareCard` | sheet |
| `Recap` | Should annual pricing include the pendant? | `Conversation` | push |
| `Recap` | iPhone roadmap Native app first: capture and conversations… | `Conversation` | push |
| `Search` | Ask Omi instead | `Chat` | push |
| `Search` | Cancel | `Main` | push |
| `Search` | What did I promise to do this week? | `Chat` | push |
| `Settings` | Appearance System | `Appearance` | push |
| `Settings` | Conversation display | `Conversations` | push |
| `Settings` | Data & privacy | `Privacy` | push |
| `Settings` | Done | `Main` | dismiss |
| `Settings` | Free plan 214 of 300 premium minutes left this month | `Plan` | push |
| `Settings` | Home screen | `Main` | push |
| `Settings` | Integrations | `Integrations` | push |
| `Settings` | Language English | `Language` | push |
| `Settings` | Memories | `Memories` | push |
| `Settings` | Notifications | `Notifications` | push |
| `Settings` | Offline recordings 12 min | `Sync` | push |
| `Settings` | Omi pendant 42% | `Device` | sheet |
| `Settings` | People 3 | `People` | push |
| `Settings` | Permissions | `Permissions` | push |
| `Settings` | Phone calls | `Call` | cover |
| `Settings` | Transcription Omi cloud | `Transcription` | push |
| `Settings` | Your voice | `Voice` | push |
| `ShareCard` | Close | `Recap` | dismiss |
| `SignIn` | Back | `Welcome` | pop |
| `SignIn` | Privacy Policy | `Consent` | push |
| `SignIn` | Terms of Service | `Consent` | push |
| `Source` | Back | `Language` | pop |
| `Source` | Continue | `Permissions` | push |
| `Source` | Skip | `Permissions` | push |
| `Speaker` | Close | `Conversation` | dismiss |
| `Speaker` | New person… | `People` | push |
| `Speaker` | ‹dynamic› | `Conversation` | push |
| `Sync` | (icon) | `Conversation` | push |
| `Sync` | Back | `Conversations` | pop |
| `TaskEdit` | Call Chitapa reminder Today at 3:14 PM · 14 s | `Conversation` | push |
| `TaskEdit` | Cancel | `Tasks` | dismiss |
| `TaskEdit` | Change default app | `Integrations` | push |
| `TaskEdit` | Save | `Tasks` | push |
| `Tasks` | Apps | `Apps` | push |
| `Tasks` | Ask Omi | `Chat` | push |
| `Tasks` | Conversations | `Conversations` | push |
| `Tasks` | Export destination | `Integrations` | push |
| `Tasks` | Home | `Main` | push |
| `Tasks` | ‹dynamic› | `TaskEdit` | sheet |
| `Transcription` | Back | `Settings` | pop |
| `Transcription` | Language English | `Language` | push |
| `TutorialAsk` | Close tutorial | `Device` | dismiss |
| `TutorialAsk` | Next | `TutorialPower` | sheet |
| `TutorialAsk` | Skip This Step | `TutorialPower` | sheet |
| `TutorialDoubleTap` | Close tutorial | `Device` | dismiss |
| `TutorialDoubleTap` | Finish | `Device` | sheet |
| `TutorialIntro` | Close tutorial | `Device` | dismiss |
| `TutorialIntro` | Start | `TutorialTranscribe` | sheet |
| `TutorialPower` | Close tutorial | `Device` | dismiss |
| `TutorialPower` | Next | `TutorialDoubleTap` | sheet |
| `TutorialPower` | Skip This Step | `TutorialDoubleTap` | sheet |
| `TutorialTranscribe` | Close tutorial | `Device` | dismiss |
| `TutorialTranscribe` | Next | `TutorialAsk` | sheet |
| `TutorialTranscribe` | Skip This Step | `TutorialAsk` | sheet |
| `Upgrade` | Close | `Plan` | dismiss |
| `Upgrade` | ‹dynamic› | `Plan` | push |
| `Voice` | Back | `Permissions` | pop |
| `Voice` | Review Answers | `VoiceReview` | push |
| `Voice` | Set Up My Voice Later | `Knows` | push |
| `VoiceAsk` | Close | `Chat` | uncover |
| `VoiceAsk` | Done | `Chat` | push |
| `VoiceReview` | Back | `Voice` | pop |
| `VoiceReview` | Continue | `Knows` | push |
| `VoiceReview` | Continue Without Saving Answers | `Knows` | push |
| `Welcome` | Get Started | `SignIn` | push |
| `Welcome` | Sign in | `SignIn` | push |
