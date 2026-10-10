---
id: data-and-account
title: Data and account
keywords: where data lives, local database, application support, sync, account, subscription, operator, architect, private cloud, sign out
sources:
  - Desktop/Sources/Rewind/Core/RewindDatabase.swift
  - Desktop/Sources/OmiSupport/DesktopLocalProfile.swift
  - Desktop/Sources/Rewind/Core/MemoryStorage.swift
  - Desktop/Sources/Rewind/Core/ActionItemStorage.swift
  - Desktop/Sources/Rewind/Core/TranscriptionStorage.swift
  - Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+NotificationsPrivacy.swift
  - Desktop/Sources/MainWindow/Pages/Settings/Components/SettingsContentView+BillingHelpers.swift
  - Desktop/Sources/MainWindow/SettingsSidebar.swift
  - Desktop/Sources/MainWindow/Pages/SettingsPage.swift
---

Omi stores this Mac's data locally first. For the signed-in user the database is ~/Library/Application Support/Omi/users/<account>/omi.db, with a Screenshots folder beside it. Omi Beta uses ~/Library/Application Support/Omi Beta/ and does not share the stable app's database.

Conversations, memories, and tasks are cached in that local database and sync with the signed-in account. Screen history is written on this Mac. Settings → Alerts & Privacy → Data Controls has Store Recordings (whether audio recordings of conversations are stored) and Private Cloud Sync. That page also says account data is encrypted and stored with Google Cloud infrastructure. Export All Data downloads a JSON copy of the account.

Account and subscription are Settings → Account & Plan. That page shows the current plan and upgrades. Plan names it offers include Operator and Architect. Sign Out is on Account.
