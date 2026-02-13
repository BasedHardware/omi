import SwiftUI

/// Settings sidebar that replaces the main sidebar when in settings
struct SettingsSidebar: View {
    @Binding var selectedSection: SettingsContentView.SettingsSection
    @Binding var selectedAdvancedSubsection: SettingsContentView.AdvancedSubsection?
    let onBack: () -> Void

    @State private var isBackHovered = false

    private let expandedWidth: CGFloat = 260
    private let iconWidth: CGFloat = 20

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Back button header
            backButton
                .padding(.top, 12)
                .padding(.horizontal, 16)

            Spacer().frame(height: 24)

            // Settings title
            Text("Settings")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 16)
                .padding(.bottom, 16)

            // Settings sections
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

            Spacer()
        }
        .frame(width: expandedWidth)
        .background(OmiColors.backgroundPrimary)
    }

    private var backButton: some View {
        HStack(spacing: 8) {
            Image(systemName: "chevron.left")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(OmiColors.textSecondary)

            Text("Back")
                .font(.system(size: 14, weight: .medium))
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
        case .advanced: return "chart.bar"
        case .about: return "info.circle"
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 17))
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
                .frame(width: iconWidth)

            Text(section.rawValue)
                .font(.system(size: 14, weight: isSelected ? .medium : .regular))
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
                .font(.system(size: 14))
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textTertiary)
                .frame(width: 16)

            Text(subsection.rawValue)
                .font(.system(size: 13, weight: isSelected ? .medium : .regular))
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

#Preview {
    SettingsSidebar(
        selectedSection: .constant(.advanced),
        selectedAdvancedSubsection: .constant(.aiUserProfile),
        onBack: {}
    )
    .preferredColorScheme(.dark)
}
