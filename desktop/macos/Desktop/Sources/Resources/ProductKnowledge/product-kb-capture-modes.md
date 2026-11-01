---
id: capture-modes
title: Capture modes
keywords: only meetings, always on, meeting only recording, meeting-only, audio recording, capture mode, microphone
sources:
  - Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+General.swift
  - Desktop/Sources/MainWindow/QueryShell/ShellListeningModeMenu.swift
  - Desktop/Sources/MainWindow/CaptureListeningLogic.swift
  - Desktop/Sources/AppState/AppState+Transcription.swift
  - Desktop/Sources/MeetingDetector.swift
  - Desktop/Sources/ConferencingApps.swift
  - Desktop/Sources/ProactiveAssistants/Services/AssistantSettings.swift
---

Audio recording has three modes: Off, Always On, and Only Meetings. The default is Only Meetings.

Off records nothing. Always On keeps the microphone recording, and system audio too on macOS 14.4 or later when that permission is granted. Only Meetings records the microphone and system audio only while a call is active. Until a call is detected it waits, and it does not keep the microphone open.

A call means a known call app is actually in a call — Zoom, Microsoft Teams, FaceTime, Webex, GoTo Meeting, Slack, Discord, WhatsApp, or Telegram — or a browser window that is a Google Meet or Teams meeting. An idle chat window does not start recording.

Change the mode after onboarding in either place:

- Top bar microphone button. The menu is Off, Always On, and Only Meetings.
- Settings → General → Audio Recording. The same three choices are the control on that card. Open Settings from the gear at the trailing edge of the top bar, or press Command-Comma.

Audio Settings… in the microphone menu opens Settings → Transcription (language and vocabulary). It does not change Only Meetings versus Always On.

Screen Capture is separate. Settings → General → Screen Capture turns screenshot capture on or off. That is not the audio mode.
