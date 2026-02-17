import SwiftUI

// MARK: - Search Data Model

struct SettingsSearchItem: Identifiable {
    let id = UUID()
    let name: String
    let keywords: [String]
    let section: SettingsContentView.SettingsSection
    let advancedSubsection: SettingsContentView.AdvancedSubsection?
    let icon: String

    var breadcrumb: String {
        if let sub = advancedSubsection {
            return "Advanced → \(sub.rawValue)"
        }
        return section.rawValue
    }

    static let allSearchableItems: [SettingsSearchItem] = [
        // General
        SettingsSearchItem(name: "Screen Analysis", keywords: ["monitor", "screenshot", "capture"], section: .general, advancedSubsection: nil, icon: "gearshape"),
        SettingsSearchItem(name: "Transcription", keywords: ["audio", "recording", "microphone", "speech"], section: .general, advancedSubsection: nil, icon: "gearshape"),
        SettingsSearchItem(name: "Notifications", keywords: ["alerts", "notify"], section: .general, advancedSubsection: nil, icon: "gearshape"),
        SettingsSearchItem(name: "Ask Omi", keywords: ["floating bar", "chat bar"], section: .general, advancedSubsection: nil, icon: "gearshape"),
        SettingsSearchItem(name: "Font Size", keywords: ["text size", "zoom", "scale"], section: .general, advancedSubsection: nil, icon: "gearshape"),
        SettingsSearchItem(name: "Reset Window Size", keywords: ["resize", "window", "default size"], section: .general, advancedSubsection: nil, icon: "gearshape"),

        // Device
        SettingsSearchItem(name: "Device", keywords: ["hardware", "omi device"], section: .device, advancedSubsection: nil, icon: "wave.3.right.circle"),
        SettingsSearchItem(name: "Bluetooth", keywords: ["bluetooth", "ble", "connect", "pair", "wireless"], section: .device, advancedSubsection: nil, icon: "wave.3.right.circle"),
        SettingsSearchItem(name: "Firmware Update", keywords: ["firmware", "flash", "device update"], section: .device, advancedSubsection: nil, icon: "wave.3.right.circle"),

        // Focus
        SettingsSearchItem(name: "Focus", keywords: ["distraction", "productivity"], section: .focus, advancedSubsection: nil, icon: "eye"),

        // Rewind
        SettingsSearchItem(name: "Rewind", keywords: ["screen history", "screenshots", "recording"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath"),
        SettingsSearchItem(name: "Excluded Apps", keywords: ["exclude", "ignore", "block apps", "blocklist"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath"),
        SettingsSearchItem(name: "Battery Optimization", keywords: ["battery", "power", "energy", "low power"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath"),
        SettingsSearchItem(name: "Data Retention", keywords: ["retention", "storage", "delete old", "keep data"], section: .rewind, advancedSubsection: nil, icon: "clock.arrow.circlepath"),

        // Transcription
        SettingsSearchItem(name: "Transcription Settings", keywords: ["language", "vocabulary", "speech"], section: .transcription, advancedSubsection: nil, icon: "waveform"),
        SettingsSearchItem(name: "Language Mode", keywords: ["language", "multilingual", "single language"], section: .transcription, advancedSubsection: nil, icon: "waveform"),
        SettingsSearchItem(name: "Custom Vocabulary", keywords: ["vocabulary", "words", "custom words", "dictionary"], section: .transcription, advancedSubsection: nil, icon: "waveform"),

        // Notifications
        SettingsSearchItem(name: "Notification Settings", keywords: ["daily summary", "frequency", "alerts"], section: .notifications, advancedSubsection: nil, icon: "bell"),
        SettingsSearchItem(name: "Notification Frequency", keywords: ["frequency", "how often", "interval"], section: .notifications, advancedSubsection: nil, icon: "bell"),
        SettingsSearchItem(name: "Focus Notifications", keywords: ["focus", "distraction", "notify focus"], section: .notifications, advancedSubsection: nil, icon: "bell"),
        SettingsSearchItem(name: "Task Notifications", keywords: ["task", "action item", "notify task"], section: .notifications, advancedSubsection: nil, icon: "bell"),
        SettingsSearchItem(name: "Advice Notifications", keywords: ["advice", "tips", "notify advice"], section: .notifications, advancedSubsection: nil, icon: "bell"),
        SettingsSearchItem(name: "Memory Notifications", keywords: ["memory", "facts", "notify memory"], section: .notifications, advancedSubsection: nil, icon: "bell"),
        SettingsSearchItem(name: "Daily Summary", keywords: ["daily", "summary", "digest", "end of day"], section: .notifications, advancedSubsection: nil, icon: "bell"),
        SettingsSearchItem(name: "Summary Time", keywords: ["time", "schedule", "when", "hour"], section: .notifications, advancedSubsection: nil, icon: "bell"),

        // Privacy
        SettingsSearchItem(name: "Privacy", keywords: ["data", "encryption", "cloud sync", "recordings"], section: .privacy, advancedSubsection: nil, icon: "lock.shield"),
        SettingsSearchItem(name: "Store Recordings", keywords: ["store", "save recordings", "audio storage"], section: .privacy, advancedSubsection: nil, icon: "lock.shield"),
        SettingsSearchItem(name: "Private Cloud Sync", keywords: ["cloud", "sync", "private cloud"], section: .privacy, advancedSubsection: nil, icon: "lock.shield"),
        SettingsSearchItem(name: "Encryption", keywords: ["encrypt", "security", "end to end"], section: .privacy, advancedSubsection: nil, icon: "lock.shield"),
        SettingsSearchItem(name: "What We Track", keywords: ["tracking", "analytics", "telemetry", "data collection"], section: .privacy, advancedSubsection: nil, icon: "lock.shield"),

        // Account
        SettingsSearchItem(name: "Account", keywords: ["profile", "email"], section: .account, advancedSubsection: nil, icon: "person.circle"),
        SettingsSearchItem(name: "Sign Out", keywords: ["sign out", "log out", "logout", "signout"], section: .account, advancedSubsection: nil, icon: "person.circle"),

        // AI Chat
        SettingsSearchItem(name: "AI Chat", keywords: ["claude", "chat settings"], section: .aiChat, advancedSubsection: nil, icon: "cpu"),
        SettingsSearchItem(name: "Ask Mode", keywords: ["ask", "act", "read only", "mode toggle"], section: .aiChat, advancedSubsection: nil, icon: "cpu"),
        SettingsSearchItem(name: "CLAUDE.md", keywords: ["claude md", "claude config", "instructions"], section: .aiChat, advancedSubsection: nil, icon: "cpu"),
        SettingsSearchItem(name: "Skills", keywords: ["skills", "plugins", "abilities"], section: .aiChat, advancedSubsection: nil, icon: "cpu"),

        // About
        SettingsSearchItem(name: "Software Updates", keywords: ["update", "auto update", "sparkle", "version", "check for updates"], section: .about, advancedSubsection: nil, icon: "info.circle"),
        SettingsSearchItem(name: "Auto-Install Updates", keywords: ["auto install", "automatic install", "download updates", "install updates"], section: .about, advancedSubsection: nil, icon: "info.circle"),
        SettingsSearchItem(name: "Version Info", keywords: ["version", "build", "app version", "build number"], section: .about, advancedSubsection: nil, icon: "info.circle"),
        SettingsSearchItem(name: "Report an Issue", keywords: ["bug", "feedback", "report", "issue"], section: .about, advancedSubsection: nil, icon: "info.circle"),

        // Advanced subsections
        SettingsSearchItem(name: "AI User Profile", keywords: ["profile", "generate"], section: .advanced, advancedSubsection: .aiUserProfile, icon: "brain"),
        SettingsSearchItem(name: "Your Stats", keywords: ["statistics", "conversations", "usage"], section: .advanced, advancedSubsection: .stats, icon: "chart.bar"),
        SettingsSearchItem(name: "Feature Tiers", keywords: ["tiers", "unlock", "features", "progress"], section: .advanced, advancedSubsection: .featureTiers, icon: "lock.shield"),
        SettingsSearchItem(name: "Focus Assistant", keywords: ["distraction", "cooldown", "glow"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill"),
        SettingsSearchItem(name: "Visual Glow Effect", keywords: ["glow", "visual", "border glow", "screen glow"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill"),
        SettingsSearchItem(name: "Focus Cooldown", keywords: ["cooldown", "delay", "focus timer"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill"),
        SettingsSearchItem(name: "Focus Analysis Prompt", keywords: ["prompt", "analysis", "focus prompt", "custom prompt"], section: .advanced, advancedSubsection: .focusAssistant, icon: "eye.fill"),
        SettingsSearchItem(name: "Task Assistant", keywords: ["tasks", "extraction", "confidence", "agent"], section: .advanced, advancedSubsection: .taskAssistant, icon: "checklist"),
        SettingsSearchItem(name: "Advice Assistant", keywords: ["tips", "suggestions", "advice"], section: .advanced, advancedSubsection: .adviceAssistant, icon: "lightbulb.fill"),
        SettingsSearchItem(name: "Memory Assistant", keywords: ["memories", "facts", "extraction"], section: .advanced, advancedSubsection: .memoryAssistant, icon: "brain.head.profile"),
        SettingsSearchItem(name: "Analysis Throttle", keywords: ["delay", "throttle", "app switch"], section: .advanced, advancedSubsection: .analysisThrottle, icon: "clock.arrow.2.circlepath"),
        SettingsSearchItem(name: "Multiple Chat Sessions", keywords: ["multi chat", "threads"], section: .advanced, advancedSubsection: .preferences, icon: "slider.horizontal.3"),
        SettingsSearchItem(name: "Compact Conversations", keywords: ["conversation view", "list"], section: .advanced, advancedSubsection: .preferences, icon: "slider.horizontal.3"),
        SettingsSearchItem(name: "Launch at Login", keywords: ["startup", "login", "boot"], section: .advanced, advancedSubsection: .preferences, icon: "slider.horizontal.3"),
        SettingsSearchItem(name: "Report Issue", keywords: ["bug", "feedback", "logs"], section: .advanced, advancedSubsection: .troubleshooting, icon: "wrench.and.screwdriver"),
        SettingsSearchItem(name: "Reset Onboarding", keywords: ["setup", "wizard", "permissions"], section: .advanced, advancedSubsection: .troubleshooting, icon: "wrench.and.screwdriver"),
    ]
}

/// Settings sidebar that replaces the main sidebar when in settings
struct SettingsSidebar: View {
    @Binding var selectedSection: SettingsContentView.SettingsSection
    @Binding var selectedAdvancedSubsection: SettingsContentView.AdvancedSubsection?
    let onBack: () -> Void

    @State private var isBackHovered = false
    @State private var searchQuery = ""
    @FocusState private var isSearchFocused: Bool

    private let expandedWidth: CGFloat = 260
    private let iconWidth: CGFloat = 20

    private var filteredSearchItems: [SettingsSearchItem] {
        guard !searchQuery.isEmpty else { return [] }
        let query = searchQuery.lowercased()
        return SettingsSearchItem.allSearchableItems.filter { item in
            item.name.lowercased().contains(query) ||
            item.keywords.contains(where: { $0.lowercased().contains(query) })
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

#Preview {
    SettingsSidebar(
        selectedSection: .constant(.advanced),
        selectedAdvancedSubsection: .constant(.aiUserProfile),
        onBack: {}
    )
    .preferredColorScheme(.dark)
}
