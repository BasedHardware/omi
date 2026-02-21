import SwiftUI

// MARK: - Search Data Model

struct SettingsSearchItem: Identifiable {
    let id = UUID()
    let name: String
    let subtitle: String
    let keywords: [String]
    let section: SettingsContentView.SettingsSection
    let advancedSubsection: SettingsContentView.AdvancedSubsection?
    let icon: String
    let settingId: String

    var breadcrumb: String {
        if let sub = advancedSubsection {
            return "Advanced \u{2192} \(sub.rawValue)"
        }
        return section.rawValue
    }

    static let allSearchableItems: [SettingsSearchItem] = [
        // General
        SettingsSearchItem(name: "Rewind", subtitle: "Screen capture and audio recording", keywords: ["monitor", "screenshot", "capture", "audio", "recording", "microphone", "speech"], section: .general, advancedSubsection: nil, icon: "gearshape", settingId: "general.rewind"),
        SettingsSearchItem(name: "Notifications", subtitle: "Proactive alerts and status", keywords: ["alerts", "notify"], section: .general, advancedSubsection: nil, icon: "gearshape", settingId: "general.notifications"),
        SettingsSearchItem(name: "Ask Omi", subtitle: "Show or hide the floating chat bar", keywords: ["floating bar", "chat bar"], section: .general, advancedSubsection: nil, icon: "gearshape", settingId: "general.askomi"),
        SettingsSearchItem(name: "Font Size", subtitle: "Adjust text size across the app", keywords: ["text size", "zoom", "scale", "reset"], section: .general, advancedSubsection: nil, icon: "gearshape", settingId: "general.fontsize"),
        SettingsSearchItem(name: "Reset Window Size", subtitle: "Restore the default window dimensions", keywords: ["resize", "window", "default size"], section: .general, advancedSubsection: nil, icon: "gearshape", settingId: "general.resetwindow"),

        // Device
        SettingsSearchItem(name: "Device", subtitle: "Connect and manage your Omi hardware device", keywords: ["hardware", "omi device"], section: .device, advancedSubsection: nil, icon: "wave.3.right.circle", settingId: "device.device"),
        SettingsSearchItem(name: "Bluetooth", subtitle: "Pair and connect via Bluetooth", keywords: ["bluetooth", "ble", "connect", "pair", "wireless"], section: .device, advancedSubsection: nil, icon: "wave.3.right.circle", settingId: "device.bluetooth"),
        SettingsSearchItem(name: "Firmware Update", subtitle: "Update your device firmware", keywords: ["firmware", "flash", "device update"], section: .device, advancedSubsection: nil, icon: "wave.3.right.circle", settingId: "device.firmware"),

        // Focus
        SettingsSearchItem(name: "Focus", subtitle: "Track your focus and distraction patterns", keywords: ["distraction", "productivity"], section: .focus, advancedSubsection: nil, icon: "eye", settingId: "focus.focus"),

        // Rewind
        SettingsSearchItem(name: "Rewind", subtitle: "Browse your screen history", keywords: ["screen history", "screenshots", "recording"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath", settingId: "rewind.rewind"),
        SettingsSearchItem(name: "Storage", subtitle: "View frame count and disk usage", keywords: ["frames", "storage", "disk", "space", "gb"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath", settingId: "rewind.storage"),
        SettingsSearchItem(name: "Excluded Apps", subtitle: "Screen capture is paused when these apps are active", keywords: ["exclude", "ignore", "block apps", "blocklist", "reset to defaults"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath", settingId: "rewind.excludedapps"),
        SettingsSearchItem(name: "Battery Optimization", subtitle: "Pause text recognition on battery to save energy", keywords: ["battery", "power", "energy", "low power"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath", settingId: "rewind.battery"),
        SettingsSearchItem(name: "Data Retention", subtitle: "How long to keep screen recordings", keywords: ["retention", "storage", "delete old", "keep data"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath", settingId: "rewind.retention"),

        // Transcription
        SettingsSearchItem(name: "Transcription Settings", subtitle: "Configure speech-to-text options", keywords: ["language", "vocabulary", "speech"], section: .transcription, advancedSubsection: nil, icon: "waveform", settingId: "transcription.settings"),
        SettingsSearchItem(name: "Language Mode", subtitle: "Choose single or multi-language transcription", keywords: ["language", "multilingual", "single language"], section: .transcription, advancedSubsection: nil, icon: "waveform", settingId: "transcription.languagemode"),
        SettingsSearchItem(name: "Custom Vocabulary", subtitle: "Improve recognition of names, brands, and technical terms", keywords: ["vocabulary", "words", "custom words", "dictionary"], section: .transcription, advancedSubsection: nil, icon: "waveform", settingId: "transcription.vocabulary"),

        // Notifications
        SettingsSearchItem(name: "Notification Settings", subtitle: "Control how often you receive notifications", keywords: ["daily summary", "frequency", "alerts"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.settings"),
        SettingsSearchItem(name: "Notification Frequency", subtitle: "How often to receive notifications", keywords: ["frequency", "how often", "interval"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.frequency"),
        SettingsSearchItem(name: "Focus Notifications", subtitle: "Show notification on focus changes", keywords: ["focus", "distraction", "notify focus"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.focus"),
        SettingsSearchItem(name: "Task Notifications", subtitle: "Show notification when a task is extracted", keywords: ["task", "action item", "notify task"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.task"),
        SettingsSearchItem(name: "Advice Notifications", subtitle: "Show notification when advice is generated", keywords: ["advice", "tips", "notify advice"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.advice"),
        SettingsSearchItem(name: "Memory Notifications", subtitle: "Show notification when a memory is extracted", keywords: ["memory", "facts", "notify memory"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.memory"),
        SettingsSearchItem(name: "Daily Summary", subtitle: "Receive a daily summary of your conversations and activities", keywords: ["daily", "summary", "digest", "end of day"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.dailysummary"),
        SettingsSearchItem(name: "Summary Time", subtitle: "When to send your daily summary", keywords: ["time", "schedule", "when", "hour"], section: .notifications, advancedSubsection: nil, icon: "bell", settingId: "notifications.summarytime"),

        // Privacy
        SettingsSearchItem(name: "Privacy", subtitle: "Control your data and privacy settings", keywords: ["data", "encryption", "cloud sync", "recordings"], section: .privacy, advancedSubsection: nil, icon: "lock.shield", settingId: "privacy.privacy"),
        SettingsSearchItem(name: "Store Recordings", subtitle: "Allow Omi to store audio recordings of your conversations", keywords: ["store", "save recordings", "audio storage"], section: .privacy, advancedSubsection: nil, icon: "lock.shield", settingId: "privacy.storerecordings"),
        SettingsSearchItem(name: "Private Cloud Sync", subtitle: "Sync your data securely to your private cloud storage", keywords: ["cloud", "sync", "private cloud"], section: .privacy, advancedSubsection: nil, icon: "lock.shield", settingId: "privacy.cloudsync"),
        SettingsSearchItem(name: "Encryption", subtitle: "Server-side encryption for your data", keywords: ["encrypt", "security", "end to end"], section: .privacy, advancedSubsection: nil, icon: "lock.shield", settingId: "privacy.encryption"),
        SettingsSearchItem(name: "What We Track", subtitle: "View analytics and telemetry data we collect", keywords: ["tracking", "analytics", "telemetry", "data collection"], section: .privacy, advancedSubsection: nil, icon: "lock.shield", settingId: "privacy.tracking"),

        // Account
        SettingsSearchItem(name: "Account", subtitle: "Your profile and email", keywords: ["profile", "email"], section: .account, advancedSubsection: nil, icon: "person.circle", settingId: "account.account"),
        SettingsSearchItem(name: "Sign Out", subtitle: "Sign out of your Omi account", keywords: ["sign out", "log out", "logout", "signout"], section: .account, advancedSubsection: nil, icon: "person.circle", settingId: "account.signout"),

        // AI Chat
        SettingsSearchItem(name: "AI Chat", subtitle: "Configure AI assistant settings", keywords: ["claude", "chat settings"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.aichat"),
        SettingsSearchItem(name: "Ask Mode", subtitle: "Show an Ask/Act toggle in the chat to control tool use", keywords: ["ask", "act", "read only", "mode toggle"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.askmode"),
        SettingsSearchItem(name: "CLAUDE.md", subtitle: "Personal instructions loaded into AI chat", keywords: ["claude md", "claude config", "instructions", "view"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.claudemd"),
        SettingsSearchItem(name: "Skills", subtitle: "Enable or disable discovered AI skills", keywords: ["skills", "plugins", "abilities", "view"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.skills"),
        SettingsSearchItem(name: "Browser Extension", subtitle: "Lets the AI use your Chrome browser with all your logged-in sessions", keywords: ["playwright", "chrome", "browser extension", "browser", "set up", "reconfigure", "token"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.browserextension"),
        SettingsSearchItem(name: "Workspace", subtitle: "Set a project directory for AI chat context", keywords: ["workspace", "project", "directory", "folder", "working directory", "claude.md"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.workspace"),
        SettingsSearchItem(name: "AI Provider", subtitle: "Choose between Agent SDK and Claude Code for AI chat", keywords: ["provider", "agent sdk", "claude code", "acp", "bridge mode"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.provider"),
        SettingsSearchItem(name: "Dev Mode", subtitle: "Developer tools and debugging options", keywords: ["developer", "debug", "dev mode", "development"], section: .aiChat, advancedSubsection: nil, icon: "cpu", settingId: "aichat.devmode"),

        // About
        SettingsSearchItem(name: "Software Updates", subtitle: "Check for and manage app updates", keywords: ["update", "auto update", "sparkle", "version", "check for updates", "check now"], section: .about, advancedSubsection: nil, icon: "info.circle", settingId: "about.updates"),
        SettingsSearchItem(name: "Automatic Updates", subtitle: "Check for updates automatically in the background", keywords: ["auto check", "background updates", "check automatically"], section: .about, advancedSubsection: nil, icon: "info.circle", settingId: "about.autoupdates"),
        SettingsSearchItem(name: "Auto-Install Updates", subtitle: "Automatically download and install updates when available", keywords: ["auto install", "automatic install", "download updates", "install updates"], section: .about, advancedSubsection: nil, icon: "info.circle", settingId: "about.autoinstall"),
        SettingsSearchItem(name: "Update Channel", subtitle: "Choose between stable and beta update channels", keywords: ["channel", "beta", "staging", "stable", "release channel"], section: .about, advancedSubsection: nil, icon: "info.circle", settingId: "about.channel"),
        SettingsSearchItem(name: "Version Info", subtitle: "Current app version and build number", keywords: ["version", "build", "app version", "build number"], section: .about, advancedSubsection: nil, icon: "info.circle", settingId: "about.version"),
        SettingsSearchItem(name: "Report an Issue", subtitle: "Help us improve Omi", keywords: ["bug", "feedback", "report", "issue"], section: .about, advancedSubsection: nil, icon: "info.circle", settingId: "about.reportissue"),

        // Advanced subsections
        SettingsSearchItem(name: "AI User Profile", subtitle: "AI-generated summary of your preferences and habits", keywords: ["profile", "generate", "generate now", "regenerate"], section: .advanced, advancedSubsection: .aiUserProfile, icon: "brain", settingId: "advanced.aiuserprofile"),
        SettingsSearchItem(name: "Your Stats", subtitle: "View your usage statistics and activity", keywords: ["statistics", "conversations", "usage"], section: .advanced, advancedSubsection: .stats, icon: "chart.bar", settingId: "advanced.stats"),
        SettingsSearchItem(name: "Feature Tiers", subtitle: "Track your progress and unlock features", keywords: ["tiers", "unlock", "features", "progress"], section: .advanced, advancedSubsection: .featureTiers, icon: "lock.shield", settingId: "advanced.featuretiers"),
        SettingsSearchItem(name: "Focus Assistant", subtitle: "Detect distractions and help you stay focused", keywords: ["distraction", "cooldown", "glow"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill", settingId: "advanced.focusassistant"),
        SettingsSearchItem(name: "Visual Glow Effect", subtitle: "Show colored border when focus changes", keywords: ["glow", "visual", "border glow", "screen glow"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill", settingId: "advanced.focusassistant.glow"),
        SettingsSearchItem(name: "Focus Cooldown", subtitle: "Minimum time between distraction alerts", keywords: ["cooldown", "delay", "focus timer"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill", settingId: "advanced.focusassistant.cooldown"),
        SettingsSearchItem(name: "Focus Analysis Prompt", subtitle: "Customize AI instructions for focus analysis", keywords: ["prompt", "analysis", "focus prompt", "custom prompt", "edit"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill", settingId: "advanced.focusassistant.prompt"),
        SettingsSearchItem(name: "Focus Excluded Apps", subtitle: "Focus coaching won't trigger for these apps", keywords: ["exclude", "ignore", "focus apps"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill", settingId: "advanced.focusassistant.excludedapps"),
        SettingsSearchItem(name: "Task Assistant", subtitle: "Extract tasks and action items from your screen", keywords: ["tasks", "extraction", "confidence", "agent"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant"),
        SettingsSearchItem(name: "Task Extraction Interval", subtitle: "How often to scan for new tasks", keywords: ["interval", "frequency", "how often", "scan"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant.interval"),
        SettingsSearchItem(name: "Task Minimum Confidence", subtitle: "Only show tasks above this confidence level", keywords: ["confidence", "threshold", "accuracy"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant.confidence"),
        SettingsSearchItem(name: "Task Extraction Prompt", subtitle: "Customize AI instructions for task extraction", keywords: ["prompt", "custom prompt", "task prompt", "test run", "test runner", "edit"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant.prompt"),
        SettingsSearchItem(name: "Task Allowed Apps", subtitle: "Tasks will only be extracted from these apps", keywords: ["allowed", "whitelist", "apps"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant.allowedapps"),
        SettingsSearchItem(name: "Browser Window Keywords", subtitle: "For browser apps, only analyze matching window titles", keywords: ["browser", "keywords", "filter", "window title"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant.browserkeywords"),
        SettingsSearchItem(name: "Task Prioritization", subtitle: "Re-score all tasks by relevance to your profile and goals", keywords: ["prioritize", "rescore", "re-score", "relevance", "ranking"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant.prioritization"),
        SettingsSearchItem(name: "Task Agent", subtitle: "Enable autonomous task management agent", keywords: ["agent", "autonomous", "task agent"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist", settingId: "advanced.taskassistant.agent"),
        SettingsSearchItem(name: "Advice Assistant", subtitle: "Get proactive tips and suggestions", keywords: ["tips", "suggestions", "advice"], section: .advanced, advancedSubsection: .adviceAssistant, icon: "lightbulb.fill", settingId: "advanced.adviceassistant"),
        SettingsSearchItem(name: "Advice Frequency", subtitle: "How often to check for advice opportunities", keywords: ["interval", "how often", "advice frequency"], section: .advanced, advancedSubsection: .adviceAssistant, icon: "lightbulb.fill", settingId: "advanced.adviceassistant.frequency"),
        SettingsSearchItem(name: "Advice Minimum Confidence", subtitle: "Only show advice above this confidence level", keywords: ["confidence", "threshold", "accuracy"], section: .advanced, advancedSubsection: .adviceAssistant, icon: "lightbulb.fill", settingId: "advanced.adviceassistant.confidence"),
        SettingsSearchItem(name: "Advice Prompt", subtitle: "Customize AI instructions for advice", keywords: ["prompt", "custom prompt", "advice prompt", "edit"], section: .advanced, advancedSubsection: .adviceAssistant, icon: "lightbulb.fill", settingId: "advanced.adviceassistant.prompt"),
        SettingsSearchItem(name: "Advice Excluded Apps", subtitle: "Advice won't be generated from these apps", keywords: ["exclude", "ignore", "advice apps"], section: .advanced, advancedSubsection: .adviceAssistant, icon: "lightbulb.fill", settingId: "advanced.adviceassistant.excludedapps"),
        SettingsSearchItem(name: "Memory Assistant", subtitle: "Extract facts and wisdom from your screen", keywords: ["memories", "facts", "extraction"], section: .advanced, advancedSubsection: .memoryAssistant, icon: "brain.head.profile", settingId: "advanced.memoryassistant"),
        SettingsSearchItem(name: "Memory Extraction Interval", subtitle: "How often to scan for new memories", keywords: ["interval", "frequency", "how often", "scan"], section: .advanced, advancedSubsection: .memoryAssistant, icon: "brain.head.profile", settingId: "advanced.memoryassistant.interval"),
        SettingsSearchItem(name: "Memory Minimum Confidence", subtitle: "Only save memories above this confidence level", keywords: ["confidence", "threshold", "accuracy"], section: .advanced, advancedSubsection: .memoryAssistant, icon: "brain.head.profile", settingId: "advanced.memoryassistant.confidence"),
        SettingsSearchItem(name: "Memory Extraction Prompt", subtitle: "Customize AI instructions for memory extraction", keywords: ["prompt", "custom prompt", "memory prompt", "edit"], section: .advanced, advancedSubsection: .memoryAssistant, icon: "brain.head.profile", settingId: "advanced.memoryassistant.prompt"),
        SettingsSearchItem(name: "Memory Excluded Apps", subtitle: "Memories won't be extracted from these apps", keywords: ["exclude", "ignore", "memory apps"], section: .advanced, advancedSubsection: .memoryAssistant, icon: "brain.head.profile", settingId: "advanced.memoryassistant.excludedapps"),
        SettingsSearchItem(name: "Analysis Throttle", subtitle: "Wait before analyzing after switching apps", keywords: ["delay", "throttle", "app switch"], section: .advanced, advancedSubsection: .analysisThrottle, icon: "clock.arrow.2.circlepath", settingId: "advanced.analysisthrottle"),
        SettingsSearchItem(name: "Goals", subtitle: "Track personal goals with AI-powered progress detection", keywords: ["goal", "target", "objective", "tracking"], section: .advanced, advancedSubsection: .goals, icon: "target", settingId: "advanced.goals"),
        SettingsSearchItem(name: "Auto-Generate Goals", subtitle: "Automatically suggest new goals daily based on your conversations and tasks", keywords: ["auto generate", "suggest goals", "daily goals"], section: .advanced, advancedSubsection: .goals, icon: "target", settingId: "advanced.goals.autogenerate"),
        SettingsSearchItem(name: "Ask Omi Floating Bar", subtitle: "Configure shortcuts and floating bar behavior", keywords: ["floating bar", "shortcuts", "push to talk"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi"),
        SettingsSearchItem(name: "AI Model", subtitle: "Choose the AI model for Ask Omi conversations", keywords: ["model", "ai", "sonnet", "opus", "claude"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.model"),
        SettingsSearchItem(name: "Background Style", subtitle: "Toggle between solid and transparent background", keywords: ["background", "solid", "transparent", "blur"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.background"),
        SettingsSearchItem(name: "Draggable Floating Bar", subtitle: "Allow repositioning the floating bar by dragging it", keywords: ["drag", "move", "reposition", "draggable"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.draggable"),
        SettingsSearchItem(name: "Ask Omi Shortcut", subtitle: "Global shortcut to open Ask Omi from anywhere", keywords: ["shortcut", "hotkey", "keyboard", "global shortcut"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.shortcut"),
        SettingsSearchItem(name: "Push to Talk", subtitle: "Hold a key to speak, release to send your question to AI", keywords: ["push to talk", "ptt", "hold to talk", "microphone key"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.ptt"),
        SettingsSearchItem(name: "Transcription Mode", subtitle: "Choose how voice input is processed", keywords: ["transcription", "mode", "voice", "dictation"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.transcriptionmode"),
        SettingsSearchItem(name: "Double-tap for Locked Mode", subtitle: "Double-tap the push-to-talk key to keep listening hands-free", keywords: ["double tap", "locked mode", "hands free", "listening"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.doubletap"),
        SettingsSearchItem(name: "Push-to-Talk Sounds", subtitle: "Play audio feedback when starting and ending voice input", keywords: ["sounds", "audio feedback", "ptt sounds"], section: .advanced, advancedSubsection: .askOmiFloatingBar, icon: "sparkles", settingId: "advanced.askomi.pttsounds"),
        SettingsSearchItem(name: "Multiple Chat Sessions", subtitle: "Create separate chat threads", keywords: ["multi chat", "threads"], section: .advanced, advancedSubsection: .preferences, icon: "slider.horizontal.3", settingId: "advanced.preferences.multichat"),
        SettingsSearchItem(name: "Compact Conversations", subtitle: "Toggle between compact and expanded conversation list", keywords: ["conversation view", "list"], section: .advanced, advancedSubsection: .preferences, icon: "slider.horizontal.3", settingId: "advanced.preferences.compact"),
        SettingsSearchItem(name: "Launch at Login", subtitle: "Start Omi automatically when you log in", keywords: ["startup", "login", "boot"], section: .advanced, advancedSubsection: .preferences, icon: "slider.horizontal.3", settingId: "advanced.preferences.launchatlogin"),
        SettingsSearchItem(name: "Report Issue", subtitle: "Send app logs and report a problem", keywords: ["bug", "feedback", "logs", "report"], section: .advanced, advancedSubsection: .troubleshooting, icon: "wrench.and.screwdriver", settingId: "advanced.troubleshooting.reportissue"),
        SettingsSearchItem(name: "Rescan Files", subtitle: "Re-index your files and update your AI profile", keywords: ["index", "reindex", "rescan", "files", "scan", "file indexing", "profile"], section: .advanced, advancedSubsection: .troubleshooting, icon: "wrench.and.screwdriver", settingId: "advanced.troubleshooting.rescanfiles"),
        SettingsSearchItem(name: "Reset Onboarding", subtitle: "Restart setup wizard and reset permissions", keywords: ["setup", "wizard", "permissions", "reset"], section: .advanced, advancedSubsection: .troubleshooting, icon: "wrench.and.screwdriver", settingId: "advanced.troubleshooting.resetonboarding"),
    ]
}

/// Settings sidebar that replaces the main sidebar when in settings
struct SettingsSidebar: View {
    @Binding var selectedSection: SettingsContentView.SettingsSection
    @Binding var selectedAdvancedSubsection: SettingsContentView.AdvancedSubsection?
    @Binding var highlightedSettingId: String?
    let onBack: () -> Void

    @State private var isBackHovered = false
    @State private var searchQuery = ""
    @FocusState private var isSearchFocused: Bool

    private let expandedWidth: CGFloat = 260
    private let iconWidth: CGFloat = 20

    private var filteredSearchItems: [SettingsSearchItem] {
        guard !searchQuery.isEmpty else { return [] }
        let words = searchQuery.lowercased().split(separator: " ").map(String.init)
        guard !words.isEmpty else { return [] }
        return SettingsSearchItem.allSearchableItems.filter { item in
            let nameLower = item.name.lowercased()
            let subtitleLower = item.subtitle.lowercased()
            let keywordsLower = item.keywords.map { $0.lowercased() }
            return words.allSatisfy { word in
                nameLower.contains(word) ||
                subtitleLower.contains(word) ||
                keywordsLower.contains(where: { $0.contains(word) })
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Back button header
            backButton
                .padding(.top, 12)
                .padding(.horizontal, 16)

            Spacer().frame(height: 24)

            // Settings title
            Text("Settings")
                .scaledFont(size: 22, weight: .bold)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 16)
                .padding(.bottom, 12)

            // Search field
            searchField
                .padding(.horizontal, 12)
                .padding(.bottom, 12)

            if searchQuery.isEmpty {
                // Normal settings sections
                ScrollView(showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(SettingsContentView.SettingsSection.allCases, id: \.self) { section in
                            SettingsSidebarItem(
                                section: section,
                                isSelected: selectedSection == section,
                                iconWidth: iconWidth,
                                onTap: {
                                    withAnimation(.easeInOut(duration: 0.15)) {
                                        selectedSection = section
                                        if section == .advanced && selectedAdvancedSubsection == nil {
                                            selectedAdvancedSubsection = .aiUserProfile
                                        }
                                    }
                                }
                            )

                            // Show Advanced subsections when Advanced is selected
                            if section == .advanced && selectedSection == .advanced {
                                ForEach(SettingsContentView.AdvancedSubsection.allCases, id: \.self) { subsection in
                                    SettingsSubsectionItem(
                                        subsection: subsection,
                                        isSelected: selectedAdvancedSubsection == subsection,
                                        iconWidth: iconWidth,
                                        onTap: {
                                            withAnimation(.easeInOut(duration: 0.15)) {
                                                selectedAdvancedSubsection = subsection
                                            }
                                        }
                                    )
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 8)
            } else {
                // Search results
                searchResultsList
                    .padding(.horizontal, 8)
            }

            Spacer()
        }
        .frame(width: expandedWidth)
        .background(OmiColors.backgroundPrimary)
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .scaledFont(size: 13)
                .foregroundColor(isSearchFocused ? OmiColors.purplePrimary : OmiColors.textTertiary)
                .animation(.easeInOut(duration: 0.15), value: isSearchFocused)

            TextField("Search settings...", text: $searchQuery)
                .textFieldStyle(.plain)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textPrimary)
                .focused($isSearchFocused)

            if !searchQuery.isEmpty {
                Button {
                    searchQuery = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(OmiColors.backgroundTertiary)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSearchFocused ? OmiColors.purplePrimary.opacity(0.5) : Color.clear, lineWidth: 1)
                )
        )
    }

    private var searchResultsList: some View {
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 2) {
                if filteredSearchItems.isEmpty {
                    Text("No results")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 20)
                } else {
                    ForEach(filteredSearchItems) { item in
                        SettingsSearchResultRow(item: item) {
                            withAnimation(.easeInOut(duration: 0.15)) {
                                selectedSection = item.section
                                if let sub = item.advancedSubsection {
                                    selectedAdvancedSubsection = sub
                                } else if item.section == .advanced {
                                    selectedAdvancedSubsection = .aiUserProfile
                                }
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
        HStack(spacing: 8) {
            Image(systemName: "chevron.left")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            Text("Back")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isBackHovered ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
        )
        .onTapGesture {
            onBack()
        }
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
    let onTap: () -> Void

    @State private var isHovered = false

    private var icon: String {
        switch section {
        case .general: return "gearshape"
        case .device: return "wave.3.right.circle"
        case .focus: return "eye"
        case .rewind: return "clock.arrow.circlepath"
        case .transcription: return "waveform"
        case .notifications: return "bell"
        case .privacy: return "lock.shield"
        case .account: return "person.circle"
        case .aiChat: return "cpu"
        case .advanced: return "chart.bar"
        case .about: return "info.circle"
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .scaledFont(size: 17)
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
                .frame(width: iconWidth)

            Text(section.rawValue)
                .scaledFont(size: 14, weight: isSelected ? .medium : .regular)
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 11)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isSelected
                      ? OmiColors.backgroundTertiary.opacity(0.8)
                      : (isHovered ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear))
        )
        .onTapGesture {
            onTap()
        }
        .onHover { hovering in
            isHovered = hovering
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
        HStack(spacing: 10) {
            // Indentation spacer
            Spacer()
                .frame(width: iconWidth + 12)

            Image(systemName: subsection.icon)
                .scaledFont(size: 14)
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
                .frame(width: 16)

            Text(subsection.rawValue)
                .scaledFont(size: 13, weight: isSelected ? .medium : .regular)
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isSelected
                      ? OmiColors.backgroundTertiary.opacity(0.6)
                      : (isHovered ? OmiColors.backgroundTertiary.opacity(0.3) : Color.clear))
        )
        .onTapGesture {
            onTap()
        }
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
        HStack(spacing: 10) {
            Image(systemName: item.icon)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(item.name)
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                Text(item.breadcrumb)
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isHovered ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
        )
        .onTapGesture {
            onTap()
        }
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
                RoundedRectangle(cornerRadius: 8)
                    .fill(isHighlighted ? OmiColors.purplePrimary.opacity(0.12) : Color.clear)
                    .animation(.easeInOut(duration: 0.3), value: isHighlighted)
                    .allowsHitTesting(false)
            )
            .onChange(of: highlightedSettingId) { _, newId in
                if newId == settingId {
                    withAnimation { isHighlighted = true }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                        withAnimation(.easeInOut(duration: 0.5)) { isHighlighted = false }
                        if highlightedSettingId == settingId { highlightedSettingId = nil }
                    }
                }
            }
    }
}

#Preview {
    SettingsSidebar(
        selectedSection: .constant(.advanced),
        selectedAdvancedSubsection: .constant(.aiUserProfile),
        highlightedSettingId: .constant(nil),
        onBack: {}
    )
    .preferredColorScheme(.dark)
}
