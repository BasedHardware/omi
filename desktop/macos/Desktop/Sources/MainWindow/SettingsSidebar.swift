import AppKit
import OmiTheme
import SwiftUI

// MARK: - Search Data Model

struct SettingsSearchItem: Identifiable {
  let id = UUID()
  let name: String
  let subtitle: String
  let keywords: [String]
  let section: SettingsContentView.SettingsSection
  let icon: String
  let settingId: String

  var breadcrumb: String {
    return section.rawValue
  }

  static let allSearchableItems: [SettingsSearchItem] = [
    // General
    SettingsSearchItem(
      name: "Rewind", subtitle: "Screen capture and audio recording",
      keywords: ["monitor", "screenshot", "capture", "audio", "recording", "microphone", "speech"],
      section: .general, icon: "gearshape", settingId: "general.rewind"),
    SettingsSearchItem(
      name: "System Audio", subtitle: "When to record audio from other apps",
      keywords: [
        "system audio", "meeting", "zoom", "google meet", "teams", "call", "capture", "recording",
        "speaker",
      ], section: .general, icon: "speaker.wave.2", settingId: "general.systemaudio"),
    SettingsSearchItem(
      name: "Notifications", subtitle: "Proactive alerts and status",
      keywords: ["alerts", "notify"], section: .general, icon: "gearshape",
      settingId: "general.notifications"),
    SettingsSearchItem(
      name: "Ask omi", subtitle: "Show or hide the floating chat bar",
      keywords: ["floating bar", "chat bar"], section: .general, icon: "gearshape",
      settingId: "general.askomi"),
    SettingsSearchItem(
      name: "Font Size", subtitle: "Adjust text size across the app",
      keywords: ["text size", "zoom", "scale", "reset"], section: .general, icon: "gearshape",
      settingId: "general.fontsize"),
    SettingsSearchItem(
      name: "Reset Window Size", subtitle: "Restore the default window dimensions",
      keywords: ["resize", "window", "default size"], section: .general, icon: "gearshape",
      settingId: "general.resetwindow"),

    // Rewind
    SettingsSearchItem(
      name: "Rewind", subtitle: "Browse your screen history",
      keywords: ["screen history", "screenshots", "recording"], section: .rewind,
      icon: "clock.arrow.circlepath", settingId: "rewind.rewind"),
    SettingsSearchItem(
      name: "Screen Capture", subtitle: "Toggle screen capture on or off",
      keywords: ["screen capture", "screenshot", "monitor", "recording", "rewind"],
      section: .rewind, icon: "rectangle.dashed.badge.record", settingId: "rewind.screencapture"),
    SettingsSearchItem(
      name: "Audio Recording", subtitle: "Toggle audio recording and transcription",
      keywords: ["audio", "microphone", "recording", "transcription", "mic"], section: .rewind,
      icon: "mic.fill", settingId: "rewind.audiorecording"),
    SettingsSearchItem(
      name: "Storage", subtitle: "View frame count and disk usage",
      keywords: ["frames", "storage", "disk", "space", "gb"], section: .rewind,
      icon: "clock.arrow.circlepath", settingId: "rewind.storage"),
    SettingsSearchItem(
      name: "Excluded Apps", subtitle: "Screen capture is paused when these apps are active",
      keywords: ["exclude", "ignore", "block apps", "blocklist", "reset to defaults"],
      section: .rewind, icon: "clock.arrow.circlepath", settingId: "rewind.excludedapps"),
    SettingsSearchItem(
      name: "Battery Optimization", subtitle: "Saves power by reducing screenshot frequency",
      keywords: ["battery", "power", "energy", "low power"], section: .rewind,
      icon: "clock.arrow.circlepath", settingId: "rewind.battery"),
    SettingsSearchItem(
      name: "Data Retention", subtitle: "How long to keep screen recordings",
      keywords: ["retention", "storage", "delete old", "keep data"], section: .rewind,
      icon: "clock.arrow.circlepath", settingId: "rewind.retention"),

    // Transcription
    SettingsSearchItem(
      name: "Transcription Settings", subtitle: "Configure speech-to-text options",
      keywords: ["language", "vocabulary", "speech"], section: .transcription, icon: "waveform",
      settingId: "transcription.settings"),
    SettingsSearchItem(
      name: "Language Mode", subtitle: "Choose single or multi-language transcription",
      keywords: ["language", "multilingual", "single language"], section: .transcription,
      icon: "waveform", settingId: "transcription.languagemode"),
    SettingsSearchItem(
      name: "Voice Assistant Languages",
      subtitle: "Languages you speak to Omi over push-to-talk",
      keywords: ["voice", "push to talk", "ptt", "language", "russian", "multilingual"],
      section: .transcription, icon: "person.wave.2",
      settingId: "transcription.voicelanguages"),
    SettingsSearchItem(
      name: "Custom Vocabulary",
      subtitle: "Improve recognition of names, brands, and technical terms",
      keywords: ["vocabulary", "words", "custom words", "dictionary"], section: .transcription,
      icon: "waveform", settingId: "transcription.vocabulary"),
    SettingsSearchItem(
      name: "Local VAD Gate", subtitle: "Skip silence to reduce transcription cost",
      keywords: ["vad", "silence", "gate", "cost", "deepgram"], section: .transcription,
      icon: "waveform", settingId: "transcription.vadgate"),

    // Notifications
    SettingsSearchItem(
      name: "Notification Settings", subtitle: "Control how often you receive notifications",
      keywords: ["daily summary", "frequency", "alerts"], section: .notifications, icon: "bell",
      settingId: "notifications.settings"),
    SettingsSearchItem(
      name: "Notification Frequency", subtitle: "How often to receive notifications",
      keywords: ["frequency", "how often", "interval"], section: .notifications, icon: "bell",
      settingId: "notifications.frequency"),
    SettingsSearchItem(
      name: "Focus Notifications", subtitle: "Show notification on focus changes",
      keywords: ["focus", "distraction", "notify focus"], section: .notifications, icon: "bell",
      settingId: "notifications.focus"),
    SettingsSearchItem(
      name: "Task Notifications",
      subtitle: "Allow interruptions when a task needs attention",
      keywords: ["task", "action item", "notify task", "interruption", "proactive"],
      section: .notifications, icon: "bell",
      settingId: "notifications.task"),
    SettingsSearchItem(
      name: "Insight Notifications", subtitle: "Show notification when an insight is generated",
      keywords: ["insight", "insights", "notify insight"], section: .notifications, icon: "bell",
      settingId: "notifications.insight"),
    SettingsSearchItem(
      name: "Memory Notifications", subtitle: "Show notification when a memory is extracted",
      keywords: ["memory", "facts", "notify memory"], section: .notifications, icon: "bell",
      settingId: "notifications.memory"),
    SettingsSearchItem(
      name: "Daily Summary",
      subtitle: "Receive a daily summary of your conversations and activities",
      keywords: ["daily", "summary", "digest", "end of day"], section: .notifications, icon: "bell",
      settingId: "notifications.dailysummary"),
    SettingsSearchItem(
      name: "Summary Time", subtitle: "When to send your daily summary",
      keywords: ["time", "schedule", "when", "hour"], section: .notifications, icon: "bell",
      settingId: "notifications.summarytime"),

    // Privacy
    SettingsSearchItem(
      name: "Privacy", subtitle: "Control your data and privacy settings",
      keywords: ["data", "encryption", "cloud sync", "recordings"], section: .privacy,
      icon: "lock.shield", settingId: "privacy.privacy"),
    SettingsSearchItem(
      name: "Store Recordings",
      subtitle: "Allow omi to store audio recordings of your conversations",
      keywords: ["store", "save recordings", "audio storage"], section: .privacy,
      icon: "lock.shield", settingId: "privacy.storerecordings"),
    SettingsSearchItem(
      name: "Private Cloud Sync", subtitle: "Sync your data securely to your private cloud storage",
      keywords: ["cloud", "sync", "private cloud"], section: .privacy, icon: "lock.shield",
      settingId: "privacy.cloudsync"),
    SettingsSearchItem(
      name: "Encryption", subtitle: "Server-side encryption for your data",
      keywords: ["encrypt", "security", "end to end"], section: .privacy, icon: "lock.shield",
      settingId: "privacy.encryption"),
    SettingsSearchItem(
      name: "What We Track", subtitle: "View analytics and telemetry data we collect",
      keywords: ["tracking", "analytics", "telemetry", "data collection"], section: .privacy,
      icon: "lock.shield", settingId: "privacy.tracking"),

    // Account
    SettingsSearchItem(
      name: "Account", subtitle: "Your profile and email", keywords: ["profile", "email"],
      section: .account, icon: "person.circle", settingId: "account.account"),
    SettingsSearchItem(
      name: "Sign Out", subtitle: "Sign out of your omi account",
      keywords: ["sign out", "log out", "logout", "signout"], section: .account,
      icon: "person.circle", settingId: "account.signout"),

    // Plan and Usage
    SettingsSearchItem(
      name: "Plan and Usage", subtitle: "Subscription status and usage limits",
      keywords: ["subscription", "billing", "plan", "usage", "stripe", "architect", "unlimited"],
      section: .planUsage, icon: "creditcard", settingId: "planusage.overview"),
    SettingsSearchItem(
      name: "Current Plan", subtitle: "See your current subscription and renewal status",
      keywords: ["current plan", "renewal", "billing"], section: .planUsage, icon: "creditcard",
      settingId: "planusage.current"),
    SettingsSearchItem(
      name: "Upgrade Plan", subtitle: "Buy Operator or Architect",
      keywords: ["upgrade", "buy", "pricing", "checkout", "architect", "operator", "unlimited"], section: .planUsage,
      icon: "creditcard", settingId: "planusage.purchase"),

    // About
    SettingsSearchItem(
      name: "Software Updates", subtitle: "Check for and manage app updates",
      keywords: ["update", "auto update", "sparkle", "version", "check for updates", "check now"],
      section: .about, icon: "info.circle", settingId: "about.updates"),
    SettingsSearchItem(
      name: "Automatic Updates", subtitle: "Check for updates automatically in the background",
      keywords: ["auto check", "background updates", "check automatically"], section: .about,
      icon: "info.circle", settingId: "about.autoupdates"),
    SettingsSearchItem(
      name: "Auto-Install Updates",
      subtitle: "Automatically download and install updates when available",
      keywords: ["auto install", "automatic install", "download updates", "install updates"],
      section: .about, icon: "info.circle", settingId: "about.autoinstall"),
    SettingsSearchItem(
      name: "Update Channel", subtitle: "Choose between stable and beta update channels",
      keywords: ["channel", "beta", "stable", "release channel"], section: .about,
      icon: "info.circle", settingId: "about.channel"),
    SettingsSearchItem(
      name: "Version Info", subtitle: "Current app version and build number",
      keywords: ["version", "build", "app version", "build number"], section: .about,
      icon: "info.circle", settingId: "about.version"),
    SettingsSearchItem(
      name: "Report an Issue", subtitle: "Help us improve omi",
      keywords: ["bug", "feedback", "report", "issue"], section: .about, icon: "info.circle",
      settingId: "about.reportissue"),

    // Advanced subsections
    SettingsSearchItem(
      name: "Reset Onboarding", subtitle: "Restart setup wizard for this app build only",
      keywords: ["reset", "onboarding", "restart", "setup"], section: .advanced,
      icon: "arrow.counterclockwise", settingId: "advanced.resetonboarding"),
    SettingsSearchItem(
      name: "AI User Profile", subtitle: "AI-generated summary of your preferences and habits",
      keywords: ["profile", "generate", "generate now", "regenerate"], section: .advanced,
      icon: "brain", settingId: "advanced.aiuserprofile"),
    SettingsSearchItem(
      name: "Your Stats", subtitle: "View your usage statistics and activity",
      keywords: ["statistics", "conversations", "usage"], section: .advanced, icon: "chart.bar",
      settingId: "advanced.stats"),
    SettingsSearchItem(
      name: "AI Provider", subtitle: "Choose between your omi account and Claude for desktop chat",
      keywords: ["provider", "agent sdk", "claude code", "acp", "bridge mode"], section: .advanced,
      icon: "cpu", settingId: "aichat.provider"),
    SettingsSearchItem(
      name: "Workspace", subtitle: "Set a project directory for desktop chat context",
      keywords: ["workspace", "project", "directory", "folder", "working directory"],
      section: .advanced, icon: "cpu", settingId: "aichat.workspace"),
    SettingsSearchItem(
      name: "Browser Extension",
      subtitle: "Lets the AI use your Chrome browser with all your logged-in sessions",
      keywords: [
        "playwright", "chrome", "browser extension", "browser", "set up", "reconfigure", "token",
      ], section: .advanced, icon: "cpu", settingId: "aichat.browserextension"),
    SettingsSearchItem(
      name: "Dev Mode", subtitle: "Developer tools and debugging options",
      keywords: ["developer", "debug", "dev mode", "development"], section: .advanced, icon: "cpu",
      settingId: "aichat.devmode"),
    SettingsSearchItem(
      name: "Goals", subtitle: "Track personal goals with AI-powered progress detection",
      keywords: ["goal", "target", "objective", "tracking"], section: .advanced, icon: "target",
      settingId: "advanced.goals"),
    SettingsSearchItem(
      name: "Auto-Generate Goals",
      subtitle: "Automatically suggest new goals daily based on your conversations and tasks",
      keywords: ["auto generate", "suggest goals", "daily goals"], section: .advanced,
      icon: "target", settingId: "advanced.goals.autogenerate"),
    SettingsSearchItem(
      name: "Ask omi Floating Bar",
      subtitle: "Configure the floating bar appearance and visibility",
      keywords: ["floating bar", "ask omi", "show bar"], section: .floatingBar, icon: "sparkles",
      settingId: "floatingbar.show"),
    SettingsSearchItem(
      name: "Background Style", subtitle: "Toggle between solid and transparent background",
      keywords: ["background", "solid", "transparent", "blur"], section: .floatingBar,
      icon: "sparkles", settingId: "floatingbar.background"),
    SettingsSearchItem(
      name: "Draggable Floating Bar",
      subtitle: "Allow repositioning the floating bar by dragging it",
      keywords: ["drag", "move", "reposition", "draggable"], section: .floatingBar,
      icon: "sparkles", settingId: "floatingbar.draggable"),
    SettingsSearchItem(
      name: "Typed Questions", subtitle: "Speak replies aloud for typed floating-bar questions",
      keywords: ["typed", "text", "speech", "tts", "audio answers"], section: .floatingBar,
      icon: "sparkles", settingId: "floatingbar.typedvoiceanswers"),
    SettingsSearchItem(
      name: "Screen Sharing in Chat",
      subtitle: "Let Ask Omi capture your screen when you ask about it",
      keywords: ["screenshot", "screen", "capture", "share screen", "vision", "see my screen"],
      section: .floatingBar, icon: "camera.viewfinder", settingId: "floatingbar.screenshare"),
    SettingsSearchItem(
      name: "Voice Speed", subtitle: "Adjust the playback speed for voice replies",
      keywords: ["voice speed", "speech speed", "playback speed", "tts speed"],
      section: .floatingBar, icon: "sparkles", settingId: "floatingbar.voicespeed"),
    SettingsSearchItem(
      name: "Shortcuts", subtitle: "Configure Open Omi and push-to-talk keyboard shortcuts",
      keywords: ["shortcuts", "keyboard", "hotkeys", "push to talk"], section: .shortcuts,
      icon: "keyboard", settingId: "floatingbar.shortcut"),
    SettingsSearchItem(
      name: "Open Omi Shortcut", subtitle: "Global shortcut to open the Omi app from anywhere",
      keywords: ["shortcut", "hotkey", "keyboard", "global shortcut"], section: .shortcuts,
      icon: "keyboard", settingId: "floatingbar.shortcut"),
    SettingsSearchItem(
      name: "Push to Talk", subtitle: "Hold a key to speak, release to send your question to AI",
      keywords: ["push to talk", "ptt", "hold to talk", "microphone key"], section: .shortcuts,
      icon: "keyboard", settingId: "floatingbar.ptt"),
    SettingsSearchItem(
      name: "Double-tap for Locked Mode",
      subtitle: "Double-tap the push-to-talk key to keep listening hands-free",
      keywords: ["double tap", "locked mode", "hands free", "listening"], section: .shortcuts,
      icon: "keyboard", settingId: "floatingbar.doubletap"),
    SettingsSearchItem(
      name: "Push-to-Talk Sounds",
      subtitle: "Play audio feedback when starting and ending voice input",
      keywords: ["sounds", "audio feedback", "ptt sounds"], section: .shortcuts, icon: "keyboard",
      settingId: "floatingbar.pttsounds"),
    SettingsSearchItem(
      name: "Multiple Chat Sessions", subtitle: "Create separate chat threads",
      keywords: ["multi chat", "threads"], section: .advanced, icon: "slider.horizontal.3",
      settingId: "advanced.preferences.multichat"),
    SettingsSearchItem(
      name: "Launch at Login", subtitle: "Start omi automatically when you log in",
      keywords: ["startup", "login", "boot"], section: .advanced, icon: "slider.horizontal.3",
      settingId: "advanced.preferences.launchatlogin"),
    SettingsSearchItem(
      name: "Report Issue", subtitle: "Send app logs and report a problem",
      keywords: ["bug", "feedback", "logs", "report"], section: .advanced,
      icon: "wrench.and.screwdriver", settingId: "advanced.troubleshooting.reportissue"),
    SettingsSearchItem(
      name: "Rescan Files", subtitle: "Re-index your files and update your AI profile",
      keywords: ["index", "reindex", "rescan", "files", "scan", "file indexing", "profile"],
      section: .advanced, icon: "wrench.and.screwdriver",
      settingId: "advanced.troubleshooting.rescanfiles"),
  ]
}

/// Settings sidebar that replaces the main sidebar when in settings
struct SettingsSidebar: View {
  @Binding var selectedSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingId: String?
  /// Closes settings. Lives on the glass so the whole left column is one panel.
  let onBack: () -> Void

  @State private var isBackHovered = false
  @State private var searchQuery = ""
  @FocusState private var isSearchFocused: Bool
  /// Drives the sliding selection highlight between nav items.
  @Namespace private var selectionNamespace

  private let expandedWidth: CGFloat = 260
  private let iconWidth: CGFloat = 20
  /// Leading inset that pushes the Back-to-app chip clear of the window traffic
  /// lights the glass now sits behind.
  fileprivate static let trafficLightClearance: CGFloat = 74
  // Merged nav: `.account` hosts Account & Plan (renders `.planUsage` content
  // too) and `.notifications` hosts Notifications & Privacy (renders `.privacy`
  // content too). The absorbed cases stay routable for deep links/automation
  // and highlight their merged item via `sidebarItem`.
  private let visibleSections: [SettingsContentView.SettingsSection] = [
    .general,
    .account,
    .transcription,
    .floatingBar,
    .notifications,
    .rewind,
    .shortcuts,
    .advanced,
    .about,
  ]

  private var filteredSearchItems: [SettingsSearchItem] {
    guard !searchQuery.isEmpty else { return [] }
    let words = searchQuery.lowercased().split(separator: " ").map(String.init)
    guard !words.isEmpty else { return [] }
    return SettingsSearchItem.allSearchableItems.filter { item in
      let nameLower = item.name.lowercased()
      let subtitleLower = item.subtitle.lowercased()
      let keywordsLower = item.keywords.map { $0.lowercased() }
      return words.allSatisfy { word in
        nameLower.contains(word) || subtitleLower.contains(word)
          || keywordsLower.contains(where: { $0.contains(word) })
      }
    }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Back to app — a chip on the glass, aligned to the right of the traffic
      // lights so the top of the panel reads as the window's toolbar row.
      backButton
        .padding(.leading, SettingsSidebar.trafficLightClearance)
        .padding(.top, 10)

      // Title
      Text("Settings")
        .scaledFont(size: OmiType.title, weight: .bold)
        .foregroundColor(OmiColors.textPrimary)
        .padding(.top, OmiSpacing.lg)
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.bottom, OmiSpacing.md)

      // Search field
      searchField
        .padding(.horizontal, OmiSpacing.md)
        .padding(.bottom, OmiSpacing.md)

      if searchQuery.isEmpty {
        // Normal settings sections
        ScrollView(showsIndicators: false) {
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            ForEach(visibleSections, id: \.self) { section in
              SettingsSidebarItem(
                section: section,
                isSelected: selectedSection.sidebarItem == section,
                iconWidth: iconWidth,
                namespace: selectionNamespace,
                onTap: {
                  OmiMotion.withGated(.spring(response: 0.34, dampingFraction: 0.82)) {
                    selectedSection = section
                  }
                }
              )

            }
          }
        }
        .padding(.horizontal, OmiSpacing.sm)
      } else {
        // Search results
        searchResultsList
          .padding(.horizontal, OmiSpacing.sm)
      }

      Spacer()
    }
    .frame(width: expandedWidth)
    .background(sidebarBackground)
  }

  /// Translucent glass panel with a hairline trailing divider — the settings
  /// nav reads as a native macOS sidebar rather than a flat opaque column.
  private var sidebarBackground: some View {
    ZStack {
      VisualEffectView(material: .sidebar, blendingMode: .behindWindow, alphaValue: 1)
      OmiColors.backgroundPrimary.opacity(0.55)
    }
    .overlay(alignment: .trailing) {
      Rectangle()
        .fill(OmiColors.border.opacity(0.35))
        .frame(width: 1)
    }
    .ignoresSafeArea()
  }

  /// "Back to app" chip on the glass — matches the toolbar's Settings chip so
  /// closing reads as the same control.
  private var backButton: some View {
    Button(action: onBack) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "arrow.left")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .frame(width: 18, height: 18)
        Text("Back to app")
          .scaledFont(size: OmiType.caption, weight: .semibold)
      }
      .foregroundColor(isBackHovered ? OmiColors.textPrimary : OmiColors.textTertiary)
      .padding(.horizontal, OmiSpacing.md)
      .frame(height: 34)
      .background(
        Capsule(style: .continuous)
          .fill(Color.white.opacity(isBackHovered ? 0.10 : 0.05))
          .overlay(Capsule(style: .continuous).stroke(Color.white.opacity(0.07), lineWidth: 1))
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      OmiMotion.withGated(.easeOut(duration: 0.12)) { isBackHovered = hovering }
    }
    .help("Back to app")
  }

  private var searchField: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "magnifyingglass")
        .scaledFont(size: OmiType.body)
        .foregroundColor(isSearchFocused ? OmiColors.accent : OmiColors.textTertiary)
        .omiAnimation(.easeInOut(duration: 0.15), value: isSearchFocused)

      TextField("Search settings...", text: $searchQuery)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)
        .focused($isSearchFocused)

      if !searchQuery.isEmpty {
        Button {
          searchQuery = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
    }
    .omiSearchFieldChrome(isFocused: isSearchFocused)
  }

  private var searchResultsList: some View {
    ScrollView(showsIndicators: false) {
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        if filteredSearchItems.isEmpty {
          Text("No results")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.xl)
        } else {
          ForEach(filteredSearchItems) { item in
            SettingsSearchResultRow(item: item) {
              OmiMotion.withGated(.easeInOut(duration: 0.15)) {
                selectedSection = item.section
              }
              searchQuery = ""
              let targetId = item.settingId
              DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                highlightedSettingId = targetId
              }
            }
          }
        }
      }
    }
  }

}

// MARK: - Settings Sidebar Item
struct SettingsSidebarItem: View {
  let section: SettingsContentView.SettingsSection
  let isSelected: Bool
  let iconWidth: CGFloat
  var namespace: Namespace.ID
  let onTap: () -> Void

  @State private var isHovered = false

  private var icon: String {
    switch section {
    case .general: return "gearshape"
    case .rewind: return "clock.arrow.circlepath"
    case .transcription: return "waveform"
    case .notifications: return "bell"
    case .privacy: return "lock.shield"
    case .account: return "person.circle"
    case .planUsage: return "creditcard"
    case .aiChat: return "cpu"
    case .floatingBar: return "sparkles"
    case .shortcuts: return "keyboard"
    case .advanced: return "chart.bar"
    case .about: return "info.circle"
    }
  }

  var body: some View {
    Group {
      if section == .aiChat {
        EmptyView()
      } else {
        Button(action: onTap) {
          HStack(spacing: OmiSpacing.md) {
            Image(systemName: icon)
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
              .frame(width: iconWidth)

            Text(section.displayTitle)
              .scaledFont(size: OmiType.body, weight: isSelected ? .semibold : .regular)
              .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)

            Spacer(minLength: 0)
          }
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.sm + 2)
          .contentShape(Rectangle())
          .background {
            ZStack {
              if isSelected {
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                  .fill(Color.white.opacity(0.10))
                  .overlay(
                    RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                      .stroke(Color.white.opacity(0.08), lineWidth: 1)
                  )
                  .matchedGeometryEffect(id: "settingsSelection", in: namespace)
              } else if isHovered {
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                  .fill(Color.white.opacity(0.05))
              }
            }
          }
        }
        .buttonStyle(.plain)
        .onHover { hovering in
          OmiMotion.withGated(.easeOut(duration: 0.12)) { isHovered = hovering }
        }
      }
    }
  }
}

// MARK: - Settings Subsection Item
struct SettingsSubsectionItem: View {
  let subsection: SettingsContentView.AdvancedSubsection
  let isSelected: Bool
  let iconWidth: CGFloat
  let onTap: () -> Void

  @State private var isHovered = false

  var body: some View {
    Button(action: onTap) {
      HStack(spacing: OmiSpacing.sm) {
        // Indentation spacer
        Spacer()
          .frame(width: iconWidth + 12)

        Image(systemName: subsection.icon)
          .scaledFont(size: OmiType.body)
          .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
          .frame(width: 16)

        Text(subsection.rawValue)
          .scaledFont(size: OmiType.body, weight: isSelected ? .medium : .regular)
          .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)

        Spacer()
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .contentShape(Rectangle())
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(
            isSelected
              ? OmiColors.backgroundTertiary.opacity(0.6)
              : (isHovered ? OmiColors.backgroundTertiary.opacity(0.3) : Color.clear))
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
  }
}

// MARK: - Settings Search Result Row
struct SettingsSearchResultRow: View {
  let item: SettingsSearchItem
  let onTap: () -> Void

  @State private var isHovered = false

  var body: some View {
    Button(action: onTap) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: item.icon)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textTertiary)
          .frame(width: 20)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(item.name)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)

          Text(item.breadcrumb)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .contentShape(Rectangle())
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isHovered ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
  }
}

// MARK: - Setting Highlight Modifier

struct SettingHighlightModifier: ViewModifier {
  let settingId: String
  @Binding var highlightedSettingId: String?
  @State private var isHighlighted = false

  func body(content: Content) -> some View {
    content
      .id(settingId)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isHighlighted ? OmiColors.accent.opacity(0.12) : Color.clear)
          .omiAnimation(.easeInOut(duration: 0.3), value: isHighlighted)
          .allowsHitTesting(false)
      )
      .onChange(of: highlightedSettingId) { _, newId in
        if newId == settingId {
          OmiMotion.withGated { isHighlighted = true }
          DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            OmiMotion.withGated(.easeInOut(duration: 0.5)) { isHighlighted = false }
            if highlightedSettingId == settingId { highlightedSettingId = nil }
          }
        }
      }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    SettingsSidebar(
      selectedSection: .constant(.advanced),
      highlightedSettingId: .constant(nil),
      onBack: {}
    )
    .preferredColorScheme(.dark)
  }
#endif
