import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  var rewindSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      Text("Manage screen history storage, excluded apps, and retention. Turn capture on or off from Listening.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textTertiary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)

      // Storage Stats
      settingsCard(settingId: "rewind.storage") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          settingsCardHeader(icon: "internaldrive.fill", title: "Storage")

          if let stats = rewindStats {
            settingRow(
              title: "Usage",
              subtitle: "\(stats.total) frames • \(RewindStorage.formatBytes(stats.storageSize))"
            ) {
              EmptyView()
            }
          } else {
            settingRow(
              title: "Usage",
              subtitle: "Loading..."
            ) {
              EmptyView()
            }
          }
        }
      }
      .task {
        rewindStats = await RewindIndexer.shared.getStats()
      }

      // Excluded Apps
      settingsCard(settingId: "rewind.excludedapps") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            settingsCardHeader(icon: "eye.slash.fill", title: "Excluded Apps")

            Spacer()

            Button("Reset to Defaults") {
              rewindSettings.resetToDefaults()
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          }

          Text("Screen capture is paused when these apps are active")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          Divider()
            .background(OmiColors.backgroundQuaternary)

          // List of excluded apps
          if rewindSettings.excludedApps.isEmpty {
            HStack {
              Spacer()
              VStack(spacing: OmiSpacing.sm) {
                Image(systemName: "checkmark.shield")
                  .scaledFont(size: 24)
                  .foregroundColor(OmiColors.textTertiary)
                Text("No apps excluded")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textTertiary)
              }
              .padding(.vertical, OmiSpacing.lg)
              Spacer()
            }
          } else {
            LazyVStack(spacing: OmiSpacing.sm) {
              ForEach(Array(rewindSettings.excludedApps).sorted(), id: \.self) { appName in
                ExcludedAppRow(
                  appName: appName,
                  onRemove: {
                    rewindSettings.includeApp(appName)
                  }
                )
              }
            }
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          // Add app section
          AppRuleEditorView(
            title: "Add App to Exclusion List",
            placeholder: "App name (e.g., Passwords)",
            addButtonTitle: "Add",
            existingApps: rewindSettings.excludedApps,
            builtInApps: TaskAssistantSettings.builtInExcludedApps,
            onAdd: { appName in
              rewindSettings.excludeApp(appName)
            }
          )
        }
      }

      // Battery Settings
      settingsCard(settingId: "rewind.battery") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          settingsCardHeader(icon: "battery.75percent", title: "Battery Optimization")
          settingRow(
            title: "Behavior",
            subtitle:
              "On battery, Omi captures your screen less often to save power while keeping text recognition accurate."
          ) {
            Text("Automatic")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
          }
        }
      }

      // Retention Settings
      settingsCard(settingId: "rewind.retention") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          settingsCardHeader(icon: "clock.fill", title: "Data Retention")
          settingRow(
            title: "Retention Period",
            subtitle: "How long to keep screen recordings"
          ) {
            SettingsMenuPicker(selection: $rewindSettings.retentionDays) {
              Text("3 days").tag(3)
              Text("7 days").tag(7)
              Text("14 days").tag(14)
              Text("30 days").tag(30)
            }
          }
        }
      }
    }
  }

  // MARK: - Transcription Section

}
