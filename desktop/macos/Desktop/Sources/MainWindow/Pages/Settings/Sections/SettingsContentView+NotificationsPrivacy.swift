import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var notificationsSection: some View {
    VStack(spacing: 20) {
      // Notifications
      settingsCard(settingId: "notifications.settings") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "bell.badge.fill")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            Text("Notifications")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $notificationsEnabled)
              .toggleStyle(.switch)
              .labelsHidden()
              .onChange(of: notificationsEnabled) { _, newValue in
                updateNotificationSettings(enabled: newValue)
              }
          }

          Text("Control how often you receive notifications")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)

          if notificationsEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            notificationFrequencySlider(settingId: "notifications.frequency")

            settingRow(
              title: "Focus Notifications", subtitle: "Show notification on focus changes",
              settingId: "notifications.focus"
            ) {
              Toggle("", isOn: $focusNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: focusNotificationsEnabled) { _, newValue in
                  FocusAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      focus: FocusSettingsResponse(notificationsEnabled: newValue)))
                }
            }

            settingRow(
              title: "Task Notifications", subtitle: "Show notification when a task is extracted",
              settingId: "notifications.task"
            ) {
              Toggle("", isOn: $taskNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: taskNotificationsEnabled) { _, newValue in
                  TaskAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      task: TaskSettingsResponse(notificationsEnabled: newValue)))
                }
            }

            settingRow(
              title: "Insight Notifications",
              subtitle: "Show notification when an insight is generated",
              settingId: "notifications.insight"
            ) {
              Toggle("", isOn: $insightNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: insightNotificationsEnabled) { _, newValue in
                  InsightAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      insight: InsightSettingsResponse(notificationsEnabled: newValue)))
                }
            }

            settingRow(
              title: "Memory Notifications",
              subtitle: "Show notification when a memory is extracted",
              settingId: "notifications.memory"
            ) {
              Toggle("", isOn: $memoryNotificationsEnabled)
                .toggleStyle(.switch)
                .labelsHidden()
                .onChange(of: memoryNotificationsEnabled) { _, newValue in
                  MemoryAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      memory: MemorySettingsResponse(notificationsEnabled: newValue)))
                }
            }
          }
        }
      }

      // Daily Summary
      settingsCard(settingId: "notifications.dailysummary") {
        VStack(alignment: .leading, spacing: 16) {
          HStack {
            Image(systemName: "text.badge.checkmark")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            Text("Daily Summary")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $dailySummaryEnabled)
              .toggleStyle(.switch)
              .labelsHidden()
              .onChange(of: dailySummaryEnabled) { _, newValue in
                updateDailySummarySettings(enabled: newValue)
              }
          }

          Text("Receive a daily summary of your conversations and activities")
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)

          if dailySummaryEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            settingRow(
              title: "Summary Time", subtitle: "When to send your daily summary",
              settingId: "notifications.summarytime"
            ) {
              Picker("", selection: $dailySummaryHour) {
                ForEach(hourOptions, id: \.self) { hour in
                  Text(formatHour(hour)).tag(hour)
                }
              }
              .pickerStyle(.menu)
              .frame(width: 100)
              .onChange(of: dailySummaryHour) { _, newValue in
                updateDailySummarySettings(hour: newValue)
              }
            }
          }
        }
      }

    }
  }

  // MARK: - Privacy Section

  var privacySection: some View {
    VStack(spacing: 20) {
      // Data Controls
      settingsCard(settingId: "privacy.storerecordings") {
        VStack(alignment: .leading, spacing: 16) {
          Text("Data Controls")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          privacyToggleRow(
            icon: "mic.fill",
            title: "Store Recordings",
            subtitle: "Allow omi to store audio recordings of your conversations",
            isOn: $recordingPermissionEnabled
          ) { newValue in
            updateRecordingPermission(newValue)
          }

          Divider()

          privacyToggleRow(
            icon: "cloud.fill",
            title: "Private Cloud Sync",
            subtitle: "Sync your data securely to your private cloud storage",
            isOn: $privateCloudSyncEnabled
          ) { newValue in
            updatePrivateCloudSync(newValue)
          }
        }
      }

      // Encryption
      settingsCard(settingId: "privacy.encryption") {
        VStack(alignment: .leading, spacing: 14) {
          HStack(spacing: 10) {
            Image(systemName: "shield.lefthalf.filled")
              .scaledFont(size: 14)
              .foregroundColor(OmiColors.purplePrimary)
              .frame(width: 20)

            Text("Encryption")
              .scaledFont(size: 14, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
          }

          HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
              .scaledFont(size: 12)
              .foregroundColor(.green)
              .frame(width: 20, alignment: .leading)

            Text("Server-side encryption")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textSecondary)

            Text("Active")
              .scaledFont(size: 10, weight: .semibold)
              .foregroundColor(.green)
              .padding(.horizontal, 5)
              .padding(.vertical, 1)
              .background(Color.green.opacity(0.15))
              .cornerRadius(3)
          }

          Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        }
      }

      // What We Track
      settingsCard(settingId: "privacy.tracking") {
        VStack(alignment: .leading, spacing: 12) {
          Button(action: {
            withAnimation(.easeInOut(duration: 0.2)) {
              isTrackingExpanded.toggle()
            }
          }) {
            HStack(spacing: 10) {
              Image(systemName: "list.bullet")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.purplePrimary)
                .frame(width: 20)

              Text("What We Track")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Spacer()

              Image(systemName: "chevron.right")
                .scaledFont(size: 11, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
                .rotationEffect(.degrees(isTrackingExpanded ? 90 : 0))
            }
          }
          .buttonStyle(.plain)

          if isTrackingExpanded {
            VStack(alignment: .leading, spacing: 6) {
              trackingItem("Onboarding steps completed")
              trackingItem("Settings changes")
              trackingItem("App installations and usage")
              trackingItem("Transcript processing events")
              trackingItem("Conversation creation and updates")
              trackingItem("Memory extraction events")
              trackingItem("Chat interactions")
              trackingItem("Speech profile creation")
              trackingItem("Focus session events")
              trackingItem("App open/close events")
            }
            .transition(.opacity)
          }
        }
      }

      // Privacy Guarantees
      settingsCard(settingId: "privacy.privacy") {
        VStack(alignment: .leading, spacing: 10) {
          HStack(spacing: 10) {
            Image(systemName: "hand.raised.fill")
              .scaledFont(size: 14)
              .foregroundColor(OmiColors.purplePrimary)
              .frame(width: 20)

            Text("Privacy Guarantees")
              .scaledFont(size: 14, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
          }

          VStack(alignment: .leading, spacing: 6) {
            privacyBullet("Anonymous tracking with randomly generated IDs")
            privacyBullet("No personal info stored in analytics")
            privacyBullet("Data is never sold or shared with third parties")
            privacyBullet("Opt out of tracking at any time")
          }
        }
      }
    }
  }

  // MARK: - Account Section

}
