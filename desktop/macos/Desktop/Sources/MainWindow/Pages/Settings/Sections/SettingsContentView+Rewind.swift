import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var rewindSection: some View {
    VStack(spacing: 20) {
      // Storage Stats
      settingsCard(settingId: "rewind.storage") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "internaldrive.fill")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Storage")
                .scaledFont(size: 15, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              if let stats = rewindStats {
                Text("\(stats.total) frames • \(RewindStorage.formatBytes(stats.storageSize))")
                  .scaledFont(size: 13)
                  .foregroundColor(OmiColors.textTertiary)
              } else {
                Text("Loading...")
                  .scaledFont(size: 13)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }

            Spacer()
          }
        }
      }
      .task {
        rewindStats = await RewindIndexer.shared.getStats()
      }

      // Excluded Apps
      settingsCard(settingId: "rewind.excludedapps") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "eye.slash.fill")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Excluded Apps")
                .scaledFont(size: 15, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Text("Screen capture is paused when these apps are active")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Button("Reset to Defaults") {
              rewindSettings.resetToDefaults()
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          // List of excluded apps
          if rewindSettings.excludedApps.isEmpty {
            HStack {
              Spacer()
              VStack(spacing: 8) {
                Image(systemName: "checkmark.shield")
                  .scaledFont(size: 24)
                  .foregroundColor(OmiColors.textTertiary)
                Text("No apps excluded")
                  .scaledFont(size: 13)
                  .foregroundColor(OmiColors.textTertiary)
              }
              .padding(.vertical, 16)
              Spacer()
            }
          } else {
            LazyVStack(spacing: 8) {
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
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "battery.75percent")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Battery Optimization")
                .scaledFont(size: 15, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Text(
                "On battery, Omi captures your screen less often to save power while keeping text recognition accurate."
              )
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Text("Automatic")
              .scaledFont(size: 13, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
          }
        }
      }

      // Retention Settings
      settingsCard(settingId: "rewind.retention") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "clock.fill")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Data Retention")
                .scaledFont(size: 15, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Text("How long to keep screen recordings")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Picker("", selection: $rewindSettings.retentionDays) {
              Text("3 days").tag(3)
              Text("7 days").tag(7)
              Text("14 days").tag(14)
              Text("30 days").tag(30)
            }
            .pickerStyle(.menu)
            .frame(width: 110)
          }
        }
      }
    }
  }

  // MARK: - Transcription Section

}
