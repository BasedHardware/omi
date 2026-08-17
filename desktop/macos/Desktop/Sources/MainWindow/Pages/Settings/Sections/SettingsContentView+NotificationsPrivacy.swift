import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

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
            .foregroundColor(Ink.secondary)

          if notificationsEnabled {
            GlassSeparator()

            notificationFrequencySlider(settingId: "notifications.frequency")

            GlassSeparator()

            // Sits under the master toggle and the frequency slider because both gate it:
            // frequency caps how often any proactive card is delivered, and this decides
            // whether live suggestions are generated at all.
            settingRow(
              title: "Live Suggestions",
              subtitle: "Suggest things in the notch, using what Omi already knows",
              settingId: "notifications.livesuggestions"
            ) {
              Toggle("", isOn: $liveSuggestionsEnabled)
                .toggleStyle(OmiToggleStyle())
                .labelsHidden()
                .onChange(of: liveSuggestionsEnabled) { _, newValue in
                  SuggestionAssistantSettings.shared.applyUserEnabledChange(newValue)
                }
            }

            GlassSeparator()

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

            GlassSeparator()

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

            GlassSeparator()

            settingRow(
              title: "Memory Notifications",
              subtitle: "Show notification when a memory is extracted",
              settingId: "notifications.memory"
            ) {
              Toggle("", isOn: $memoryNotificationsEnabled)
                .toggleStyle(OmiToggleStyle())
                .labelsHidden()
                .onChange(of: memoryNotificationsEnabled) { _, newValue in
                  MemoryAssistantSettings.shared.applyUserSettingChange(.notificationsEnabled, value: newValue)
                  SettingsSyncManager.shared.pushPartialUpdate(
                    AssistantSettingsResponse(
                      memory: MemorySettingsResponse(notificationsEnabled: newValue)))
                }
            }
          }
        }
      }

      // Integration suggestions sit inside the master gate because the feature
      // genuinely depends on it: `IntegrationNudgeCoordinator.isEnabledNow`
      // requires notifications to be on, so showing this switched ON beside a
      // disabled master toggle would promise a feature that cannot run.
      if notificationsEnabled {
        // Integration suggestions
        settingsCard(settingId: "notifications.integrationsuggestions") {
          VStack(alignment: .leading, spacing: OmiSpacing.lg) {
            HStack {
              settingsCardHeader(icon: "sparkles.rectangle.stack", title: "Integration Suggestions")

              Spacer()

              // `@AppStorage` already persists to the key the coordinator reads;
              // a second writer on one key only invites drift.
              Toggle("", isOn: $integrationNudgesEnabled)
                .toggleStyle(OmiToggleStyle())
                .labelsHidden()
            }

            Text(
              "When you open an app Omi can connect to — Gmail, Notion, ChatGPT — occasionally offer the "
                + "connection, with what it would do for you. At most a few times per integration."
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)

            if integrationNudgesEnabled {
              GlassSeparator()

              settingRow(
                title: "Reset all suggestion history",
                subtitle:
                  "Clears every integration's suggestion history, including ones you hid, so Omi can offer them again",
                settingId: "notifications.integrationsuggestions.reset"
              ) {
                Button("Reset") {
                  IntegrationNudgeStore.shared.resetAll()
                }
                .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
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
            .foregroundColor(Ink.secondary)

          if dailySummaryEnabled {
            GlassSeparator()

            settingRow(
              title: "Summary Time", subtitle: "When to send your daily summary (hour only)",
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
                // Storage is hour-only; snap minutes to :00 in the control so 20:45 never
                // appears as a saved value that reopens as 20:00.
                let canonical = SettingsControlMetrics.canonicalizeDailySummaryTime(selectedTime)
                if canonical != selectedTime {
                  dailySummaryTime = canonical
                }
                let hour = SettingsControlMetrics.dailySummaryHour(from: canonical)
                guard hour != dailySummaryHour else { return }
                dailySummaryHour = hour
                updateDailySummarySettings(hour: hour)
              }
            }
          }
        }
      }

    }
    // These three toggles are seeded from their local singletons when the pane is constructed,
    // but `loadBackendSettings()` then runs `SettingsSyncManager.syncFromServer()`, which is
    // server-authoritative and rewrites those same singletons underneath us. Without this the
    // switches kept painting the pre-sync values — a per-device answer to a per-account
    // question — until the next relaunch. The sync manager already announces itself; this is
    // the pane agreeing to listen.
    .onReceive(NotificationCenter.default.publisher(for: .assistantSettingsDidSyncFromServer)) { _ in
      syncNotificationTogglesFromAssistantSettings()
    }
  }

  /// Re-reads the assistant notification toggles from their stores. A sync that agrees with the
  /// pane assigns nothing, so the common case does not re-enter the `onChange` handlers above; a
  /// sync that corrects the pane does, and the resulting partial update restates the value the
  /// server just supplied, which is idempotent.
  func syncNotificationTogglesFromAssistantSettings() {
    taskNotificationsEnabled = TaskAssistantSettings.shared.notificationsEnabled
    insightNotificationsEnabled = InsightAssistantSettings.shared.notificationsEnabled
    memoryNotificationsEnabled = MemoryAssistantSettings.shared.notificationsEnabled
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

          GlassSeparator()

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
              .foregroundColor(Ink.listeningGreen)
              .frame(width: 20, alignment: .leading)

            Text("Server-side encryption")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)

            Text("Active")
              .scaledFont(size: OmiType.micro, weight: .semibold)
              .foregroundColor(Ink.listeningGreen)
              .padding(.horizontal, OmiSpacing.xxs)
              .padding(.vertical, OmiSpacing.hairline)
              .background(Ink.listeningGreen.opacity(0.15))
              .cornerRadius(OmiChrome.stripRadius)
          }

          Text("Your data is encrypted and stored securely with Google Cloud infrastructure.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
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
                .foregroundColor(Ink.secondary)
                .frame(width: 20)

              Text("What We Track")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(Ink.primary)

              Spacer()

              Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundColor(Ink.secondary)
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
              .foregroundColor(Ink.secondary)
              .frame(width: 20)

            Text("Privacy Guarantees")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)
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
