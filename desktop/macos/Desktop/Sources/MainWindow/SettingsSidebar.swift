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
    section.displayTitle
  }

  static let allSearchableItems: [SettingsSearchItem] = [
    // General
    SettingsSearchItem(
      name: "Rewind", subtitle: "Screen capture and audio recording",
      keywords: ["monitor", "screenshot", "capture", "audio", "recording", "microphone", "speech"],
      section: .general, icon: "gearshape", settingId: "general.screencapture"),
    SettingsSearchItem(
      name: "Notifications", subtitle: "macOS permission and banner status",
      keywords: ["alerts", "notify", "banners", "system settings", "permission"], section: .general,
      icon: "gearshape",
      settingId: "general.notifications"),
    SettingsSearchItem(
      name: "Ask omi", subtitle: "Show or hide the floating chat bar",
      keywords: ["floating bar", "chat bar"], section: .general, icon: "gearshape",
      settingId: "general.askomi"),
    SettingsSearchItem(
      name: "Interface Sounds", subtitle: "Sounds for important arrivals and completions",
      keywords: ["sound", "sounds", "audio", "chime", "mute", "silence", "effects"],
      section: .general, icon: "speaker.wave.2", settingId: "general.interfacesounds"),
    SettingsSearchItem(
      name: "Font Size", subtitle: "Adjust text size across the app",
      keywords: ["text size", "zoom", "scale", "reset"], section: .general, icon: "gearshape",
      settingId: "general.fontsize"),
    SettingsSearchItem(
      name: "Reset Window Size", subtitle: "Restore the default window dimensions",
      keywords: ["resize", "window", "default size"], section: .general, icon: "gearshape",
      settingId: "general.fontsize"),

    // Rewind
    SettingsSearchItem(
      name: "Rewind", subtitle: "Browse your screen history",
      keywords: ["screen history", "screenshots", "recording"], section: .rewind,
      icon: "clock.arrow.circlepath", settingId: "rewind.rewind"),
    SettingsSearchItem(
      name: "Screen Capture", subtitle: "Toggle screen capture on or off",
      keywords: ["screen capture", "screenshot", "monitor", "recording", "rewind"],
      section: .general, icon: "rectangle.dashed.badge.record", settingId: "general.screencapture"),
    SettingsSearchItem(
      name: "Audio Recording", subtitle: "Off, Always On, or Only Meetings",
      keywords: [
        "audio", "microphone", "recording", "transcription", "mic", "meeting", "zoom", "google meet",
        "teams", "call", "system audio",
      ], section: .general,
      icon: "mic.fill", settingId: "general.audiorecording"),
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
    SettingsSearchItem(
      name: "Meeting Screenshots", subtitle: "Add screenshots of what was on screen to meeting notes",
      keywords: ["meeting", "screenshots", "notes", "banner", "photos"], section: .rewind,
      icon: "photo.on.rectangle.angled", settingId: "rewind.meetingnotescreenshots"),

    // Transcription
    SettingsSearchItem(
      name: "Transcription Settings", subtitle: "Configure speech-to-text options",
      keywords: ["language", "vocabulary", "speech"], section: .transcription, icon: "waveform",
      settingId: "transcription.languagemode"),
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
      name: "Integration Notifications",
      subtitle: "Occasionally offer to connect an app Omi can use — Gmail, Notion, ChatGPT",
      keywords: ["integration", "suggestions", "connect", "gmail", "notion", "nudge"],
      section: .notifications, icon: "bell",
      settingId: "notifications.integrationsuggestions"),
    SettingsSearchItem(
      name: "Reset Integration Suggestions",
      subtitle: "Clear every integration's suggestion history so Omi can offer them again",
      keywords: ["reset", "integration", "suggestions", "history", "again"],
      section: .advanced, icon: "wrench.and.screwdriver",
      settingId: "advanced.troubleshooting.resetintegrationsuggestions"),
    SettingsSearchItem(
      name: "Daily Summary",
      subtitle: "Receive a daily summary of your conversations and activities",
      keywords: ["daily", "summary", "digest", "end of day"], section: .notifications, icon: "bell",
      settingId: "notifications.dailysummary"),
    SettingsSearchItem(
      name: "Summary Time", subtitle: "When to send your daily summary (hour only)",
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
      settingId: "privacy.storerecordings"),
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

    // Referral
    SettingsSearchItem(
      name: "Refer a Friend", subtitle: "Share one free month of Operator",
      keywords: ["refer", "referral", "friend", "gift", "free month", "share link"],
      section: .referral, icon: "gift", settingId: "referral.link"),

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
      name: "Omi Beta", subtitle: "Install the separate Omi Beta app beside this one",
      keywords: ["channel", "beta", "stable", "release channel", "omi beta"], section: .about,
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
    // HIDDEN DELIBERATELY (Nik, 2026-08-25): search entries for hidden floating-bar rows.
    // SettingsSearchItem(
    // name: "Notification Previews",
    // subtitle: "Show assistant notifications under the Floating Bar",
    // keywords: ["notification preview", "floating bar notification", "mute preview", "focus", "dnd"],
    // section: .floatingBar, icon: "sparkles", settingId: "floatingbar.notificationpreviews"),
    // SettingsSearchItem(
    // name: "Background Style", subtitle: "Toggle between solid and transparent background",
    // keywords: ["background", "solid", "transparent", "blur"], section: .floatingBar,
    // icon: "sparkles", settingId: "floatingbar.background"),
    // SettingsSearchItem(
    // name: "Draggable Floating Bar",
    // subtitle: "Allow repositioning the floating bar by dragging it",
    // keywords: ["drag", "move", "reposition", "draggable"], section: .floatingBar,
    // icon: "sparkles", settingId: "floatingbar.draggable"),
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

enum SettingsSidebarMetrics {
  /// The settings sidebar is a **table of contents**, not a content column.
  ///
  /// It was 260 — the width of the app's *main* sidebar, which carries conversation titles and has
  /// something to do with the room. Nine section names do not, and that width spent the difference
  /// on whitespace to the right of "About" while the pane beside it is the thing anyone reads.
  ///
  /// The value is **derived from the longest label rather than chosen**, because this row truncates
  /// (`lineLimit(1)`, `.tail`) and a truncated item in a table of contents is worse than a wide one.
  /// The longest merged label is deliberately concise, so the table of contents
  /// can stay narrow without truncating or stealing room from the settings pane.
  static let expandedWidth: CGFloat = 208

  /// Headroom over the measured label requirement. See `expandedWidth`: a zero-slack fit truncated
  /// on a real build, so the fit is held open by this rather than by luck.
  static let labelSlack: CGFloat = 12
  static let horizontalInset: CGFloat = OmiSpacing.sm
  static let itemAvailableWidth = expandedWidth - 2 * horizontalInset
}

/// **The rows this list actually shows**, as a value rather than a literal inside a `body`.
///
/// `ShellDestination.unreachable()` reads it: `Permissions` is an established page whose only way in
/// is a row here, so "the row exists" has to be something a test can hold. Delete it and the
/// reachability check names the page that lost its door instead of leaving it to be discovered in
/// the app (INV-NAV-1).
enum SettingsSidebarRoutes {
  /// Merged nav: `.account` hosts Account & Plan (renders `.planUsage` content
  /// too) and `.notifications` hosts Notifications & Privacy (renders `.privacy`
  /// content too). The absorbed cases stay routable for deep links/automation
  /// and highlight their merged item via `sidebarItem`.
  ///
  /// Capture and account first, then the things you tune, with Permissions beside
  /// Notifications because both are access. Shortcuts / Advanced / About stay at the foot.
  static let visibleSections: [SettingsContentView.SettingsSection] = [
    .general,
    .account,
    .transcription,
    .rewind,
    .floatingBar,
    .notifications,
    .permissions,
    .shortcuts,
    .advanced,
    .referral,
    .about,
  ]
}

/// Settings sidebar that replaces the main sidebar when in settings
struct SettingsSidebar: View {
  @Binding var selectedSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingId: String?
  let onBack: () -> Void
  @ObservedObject var appState: AppState

  @State private var isBackHovered = false
  @State private var searchQuery = ""
  @FocusState private var isSearchFocused: Bool

  private let iconWidth: CGFloat = 20
  private let visibleSections = SettingsSidebarRoutes.visibleSections

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
      // Back button header
      backButton
        .padding(.top, OmiSpacing.md)
        .padding(.horizontal, OmiSpacing.lg)

      Spacer().frame(height: OmiSpacing.xxl)

      // Settings title
      Text("Settings")
        .scaledFont(size: OmiType.heading, weight: .bold)
        .foregroundColor(Ink.primary)
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
                showsMissingPermissionNotice: section == .permissions && appState.hasMissingPermissions,
                onTap: {
                  OmiMotion.withGated(.easeInOut(duration: 0.15)) {
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
    .frame(width: SettingsSidebarMetrics.expandedWidth)
    // A half-step of shading, and deliberately not a second material: the host already wears the
    // glass (`PageGlassLane` in modern Settings, `LegacySidebarSurface` in old Home), and a
    // `.regularMaterial` here would be a within-window blur stacked on it.
    .background(Ink.rowFill)
  }

  private var searchField: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "magnifyingglass")
        .scaledFont(size: OmiType.body)
        .foregroundColor(isSearchFocused ? Ink.accent : Ink.secondary)
        .omiAnimation(.easeInOut(duration: 0.15), value: isSearchFocused)

      TextField("Search", text: $searchQuery)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
        .focused($isSearchFocused)
        .straysTypingHere($isSearchFocused)

      if !searchQuery.isEmpty {
        Button {
          searchQuery = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.sm)
    .background(
      RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
        .fill(Ink.wash)
        .overlay(
          RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
            // Focused takes the one accent at full strength; at rest it is a control outline, which
            // is `Ink.hairline` and not `Ink.separator` — a field is something you type into.
            .strokeBorder(isSearchFocused ? Ink.accent : Ink.hairline, lineWidth: 1)
        )
    )
  }

  private var searchResultsList: some View {
    ScrollView(showsIndicators: false) {
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        if filteredSearchItems.isEmpty {
          Text("No results")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
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

  private var backButton: some View {
    Button(action: onBack) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "chevron.left")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.secondary)

        Text("Back")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.secondary)

        Spacer()
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .contentShape(Rectangle())
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
          .fill(isBackHovered ? Ink.rowHover : Color.clear)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isBackHovered = hovering
    }
  }
}

// MARK: - Settings Sidebar Item
struct SettingsSidebarItem: View {
  let section: SettingsContentView.SettingsSection
  let isSelected: Bool
  let iconWidth: CGFloat
  var showsMissingPermissionNotice: Bool = false
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
    case .advanced: return "cpu"
    case .referral: return "gift"
    case .about: return "info.circle"
    case .permissions: return PermissionNavSymbol.outline
    }
  }

  var body: some View {
    Group {
      if section == .aiChat {
        EmptyView()
      } else {
        Button(action: onTap) {
          // The settings kit's row metrics rather than generic spacing tokens, so a row in the
          // table of contents and a row in the pane beside it are the same object at the same
          // rhythm — and so the narrower sidebar keeps the longest label off its own edge.
          HStack(spacing: SettingsGlassMetrics.rowContentSpacing) {
            Image(systemName: icon)
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(isSelected ? Ink.surface : Ink.secondary)
              .frame(width: iconWidth)

            Text(section.displayTitle)
              .scaledFont(size: OmiType.body, weight: isSelected ? .medium : .regular)
              .foregroundColor(isSelected ? Ink.surface : Ink.primary)
              .lineLimit(1)
              .truncationMode(.tail)
              .layoutPriority(1)

            if showsMissingPermissionNotice {
              Image(systemName: PermissionNavSymbol.missingNotice)
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundColor(SettingsInk.notice)
                .accessibilityHidden(true)
            }

            Spacer(minLength: 0)
          }
          .padding(.horizontal, SettingsGlassMetrics.rowHorizontalPadding)
          .padding(.vertical, SettingsGlassMetrics.rowVerticalPadding)
          .contentShape(Rectangle())
          .background(
            // Selection is the one thing on this pane that is actionable and is not already a
            // button, which is exactly what the single accent is for. A row *shaded* rather than
            // filled cannot be told apart from a hover on a surface this light — the shading a dark
            // palette could spend here does not exist on glass.
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
              .fill(
                isSelected
                  ? AnyShapeStyle(Ink.accent)
                  : AnyShapeStyle(isHovered ? Ink.rowHover : Color.clear))
          )
        }
        .buttonStyle(.plain)
        .onHover { hovering in
          isHovered = hovering
        }
        .accessibilityAddTraits(isSelected ? [.isSelected, .isButton] : .isButton)
        .accessibilityLabel(
          Text(
            showsMissingPermissionNotice
              ? "\(section.displayTitle), permissions required"
              : section.displayTitle)
        )
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
          .foregroundColor(isSelected ? Ink.surface : Ink.secondary)
          .frame(width: 16)

        Text(subsection.rawValue)
          .scaledFont(size: OmiType.body, weight: isSelected ? .medium : .regular)
          .foregroundColor(isSelected ? Ink.surface : Ink.primary)

        Spacer()
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .contentShape(Rectangle())
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
          .fill(
            isSelected
              ? AnyShapeStyle(Ink.accent)
              : AnyShapeStyle(isHovered ? Ink.rowHover : Color.clear))
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
    .accessibilityAddTraits(isSelected ? [.isSelected, .isButton] : .isButton)
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
          .foregroundColor(Ink.secondary)
          .frame(width: 20)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(item.name)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)

          Text(item.breadcrumb)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }

        Spacer()
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .contentShape(Rectangle())
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
          .fill(isHovered ? Ink.rowHover : Color.clear)
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
        // The "here it is" flash after a search jump: a wash of the one accent plus its edge, cut to
        // the card's own corner so the flash lands on the card rather than beside it.
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
          .fill(isHighlighted ? Ink.accent.opacity(0.12) : Color.clear)
          .overlay(
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
              .strokeBorder(isHighlighted ? Ink.accent : Color.clear, lineWidth: 1)
          )
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
      onBack: {},
      appState: AppState()
    )
    .preferredColorScheme(.light)
  }
#endif
