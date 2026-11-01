---
id: surfaces
title: App surfaces
keywords: conversations, tasks, memories, daily recap, rewind, screen history, chat, apps, integrations, brain map, activity
sources:
  - Desktop/Sources/MainWindow/TopNavigationDestinations.swift
  - Desktop/Sources/MainWindow/QueryShell/ActivityDestinationChip.swift
  - Desktop/Sources/MainWindow/MemoryHubDestination.swift
  - Desktop/Sources/MainWindow/ChatFirst/ChatFirstRoute.swift
  - Desktop/Sources/MainWindow/Dashboard/DailyRecapPage.swift
  - Desktop/Sources/Rewind/UI/RewindSearchBar.swift
  - Desktop/Sources/Rewind/UI/RewindSearchLayout.swift
  - Desktop/Sources/MainWindow/SettingsSidebar.swift
---

The top bar is Chat, Memories, Tasks, and Apps, plus a Settings gear.

- Chat is where you talk to Omi. A daily recap is not its own pill. Open it from the recap row in Chat. The page title is Daily recap. When that summary is sent is Settings → Alerts & Privacy → Daily Summary.
- Memories opens captured history. A row on that page switches among Activity, Conversations, Memories, Rewind, and Brain Map. Conversations are spoken audio. Memories are saved facts. Activity is the timeline of what was captured. Brain Map is the graph of those memories.
- Rewind is the screen-history player on that same row. Its search field reads "Search what you've seen and heard…". That search is what was on screen, not the conversation list.
- Tasks is the list of commitments Omi heard.
- Apps is connectors, imports, and exports.

Settings sections include General (screen capture and audio recording), Account & Plan, Transcription, Rewind, Floating Bar, Alerts & Privacy, Permissions, Shortcuts, AI & Automation, Refer a Friend, and About.
