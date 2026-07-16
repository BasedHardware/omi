import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var notificationsSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Notifications
      settingsCard(settingId: "notifications.settings") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            settingsCardHeader(icon: "bell.badge.fill", title: "Notifications")

            Spacer()

            Toggle("", isOn: $notificationsEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: notificationsEnabled) { _, newValue in
                updateNotificationSettings(enabled: newValue)
              }
          }

          Text("Control how often you receive notifications")
            .scaledFont(size: OmiType.body)
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
                .toggleStyle(OmiToggleStyle())
                .labelsHidden()
                .onChange(of: focusNotificationsEnabled) { _, newValue in
                  FocusAssistantSettings.shared.notificationsEnabled = newValue
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      focus: FocusSettingsResponse(notificationsEnabled: newValue)))
                }
            }

            settingRow(
              title: "Task Notifications",
              subtitle: "Allow interruptions when a task needs attention",
              settingId: "notifications.task"
            ) {
              Toggle("", isOn: $taskNotificationsEnabled)
                .toggleStyle(OmiToggleStyle())
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
                .toggleStyle(OmiToggleStyle())
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
                .toggleStyle(OmiToggleStyle())
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
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            settingsCardHeader(icon: "text.badge.checkmark", title: "Daily Summary")

            Spacer()

            Toggle("", isOn: $dailySummaryEnabled)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .onChange(of: dailySummaryEnabled) { _, newValue in
                updateDailySummarySettings(enabled: newValue)
              }
          }

          Text("Receive a daily summary of your conversations and activities")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          if dailySummaryEnabled {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            settingRow(
              title: "Summary Time", subtitle: "When to send your daily summary",
              settingId: "notifications.summarytime"
            ) {
              DatePicker(
                "",
                selection: $dailySummaryTime,
                displayedComponents: .hourAndMinute
              )
              .datePickerStyle(.stepperField)
              .labelsHidden()
              .fixedSize()
              .onChange(of: dailySummaryTime) { _, selectedTime in
                let hour = SettingsControlMetrics.dailySummaryHour(from: selectedTime)
                guard hour != dailySummaryHour else { return }
                dailySummaryHour = hour
                updateDailySummarySettings(hour: hour)
              }
            }
          }
        }
      }

    }
  }

  // MARK: - Privacy Section

  var privacySection: some View {
    VStack(spacing: OmiSpacing.xl) {
      // Data Controls
      settingsCard(settingId: "privacy.storerecordings") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          settingsCardHeader(icon: "shield", title: "Data Controls")

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
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          settingsCardHeader(icon: "shield.lefthalf.filled", title: "Encryption")

          HStack(spacing: OmiSpacing.sm) {
            Image(systemName: "checkmark.circle.fill")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(.green)
              .frame(width: 20, alignment: .leading)

            Text("Server-side encryption")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)

            Text("Active")
              .scaledFont(size: OmiType.micro, weight: .semibold)
              .foregroundColor(.green)
              .padding(.horizontal, OmiSpacing.xxs)
              .padding(.vertical, OmiSpacing.hairline)
              .background(Color.green.opacity(0.15))
              .cornerRadius(OmiChrome.stripRadius)
          }

          Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }
      }

      // What We Track
      settingsCard(settingId: "privacy.tracking") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          Button(action: {
            OmiMotion.withGated(.easeInOut(duration: 0.2)) {
              isTrackingExpanded.toggle()
            }
          }) {
            HStack(spacing: OmiSpacing.sm) {
              Image(systemName: "list.bullet")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textSecondary)
                .frame(width: 20)

              Text("What We Track")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Spacer()

              Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
                .rotationEffect(.degrees(isTrackingExpanded ? 90 : 0))
            }
          }
          .buttonStyle(.plain)

          if isTrackingExpanded {
            VStack(alignment: .leading, spacing: OmiSpacing.xs) {
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
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          HStack(spacing: OmiSpacing.sm) {
            Image(systemName: "hand.raised.fill")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
              .frame(width: 20)

            Text("Privacy Guarantees")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
          }

          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
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
