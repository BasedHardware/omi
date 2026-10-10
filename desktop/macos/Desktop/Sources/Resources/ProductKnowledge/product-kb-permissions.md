---
id: permissions
title: Permissions
keywords: permissions, screen recording, microphone permission, accessibility, system audio, full disk access, notifications, grant permission
sources:
  - Desktop/Sources/MainWindow/Pages/PermissionsPage.swift
  - Desktop/Sources/MainWindow/Pages/PermissionsPageChrome.swift
  - Desktop/Sources/MainWindow/Pages/SettingsPage.swift
  - Desktop/Sources/MainWindow/TopNavigationDestinations.swift
  - Desktop/Sources/Providers/ChatToolExecutor.swift
  - Desktop/Sources/AppState/AppState+Permissions.swift
---

Open Settings (the top-bar gear, or Command-Comma) and choose Permissions to grant or re-grant access. Required: Microphone, Screen Recording, System Audio, Notifications, and Accessibility. Optional, one feature each: Bluetooth, Full Disk Access, and Automation. A missing required grant shows as Not Granted.

If macOS already refused a prompt, it will not ask again. Use that row's System Settings path, or the reset steps on the row.

- Microphone: System Settings → Privacy & Security → Microphone. Required for voice recording and transcription.
- Screen Recording: System Settings → Privacy & Security → Screen Recording. Required to capture the screen.
- System Audio (macOS 14.4 and later): on the System Audio row, click Test Access. If System Settings opens, enable Omi under Screen & System Audio Recording, come back, and test again. Older macOS does not offer this.
- Notifications: System Settings → Notifications → Omi. Set the style to Banners to see alerts. Omi can request permission but cannot turn it off; switching notifications off in the app opens System Settings.
- Accessibility: System Settings → Privacy & Security → Accessibility. This lets Omi name the document, page, or file in front, not only the frontmost app. If the switch looks on but Omi says the grant is broken (common after an update or re-sign), remove Omi from the list and add it again.
- Full Disk Access: System Settings → Privacy & Security → Full Disk Access. Optional. Needed to read Messages or Mail headers.
- Automation: System Settings → Privacy & Security → Automation. Optional. Needed to control another app, such as Messages.

You can also ask chat to check or request one named permission. You still confirm the system prompt or the Settings switch yourself.
