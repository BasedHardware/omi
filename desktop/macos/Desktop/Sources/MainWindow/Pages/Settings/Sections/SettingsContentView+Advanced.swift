import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

extension SettingsContentView {
  func advancedCategoryHeader(title: String, icon: String) -> some View {
    HStack(spacing: 10) {
      Image(systemName: icon)
        .scaledFont(size: 16)
        .foregroundColor(OmiColors.purplePrimary)
      Text(title)
        .scaledFont(size: 18, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)
      Spacer()
    }
    .padding(.top, 16)
  }

  var advancedSection: some View {
    VStack(spacing: 24) {
      advancedCategoryHeader(title: "AI Setup", icon: "cpu")
      aiSetupSubsection
      advancedCategoryHeader(title: "Profile & Stats", icon: "brain")
      profileAndStatsSubsection
      advancedCategoryHeader(title: "Reset Onboarding", icon: "arrow.counterclockwise")
      resetOnboardingSubsection
      advancedCategoryHeader(title: "Goals", icon: "target")
      goalsSubsection
      advancedCategoryHeader(title: "Preferences", icon: "slider.horizontal.3")
      preferencesSubsection
      advancedCategoryHeader(title: "Troubleshooting", icon: "wrench.and.screwdriver")
      troubleshootingSubsection
      advancedCategoryHeader(title: "Developer API Keys", icon: "key")
      developerKeysSubsection

      advancedCategoryHeader(title: "Dev Tools", icon: "hammer")
      devToolsSubsection
    }
  }

  // MARK: - Dev Tools Subsection

  var devToolsSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.devtools.chatlab") {
        HStack(spacing: 12) {
          Image(systemName: "flask.fill")
            .scaledFont(size: 16)
            .foregroundColor(OmiColors.purplePrimary)
          VStack(alignment: .leading, spacing: 4) {
            Text("Chat Prompt Lab")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Iterate on chat system prompts with real questions, AI grading, and production ratings")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
          Button("Open") {
            ChatLabWindowManager.shared.openWindow(chatProvider: chatProvider)
          }
          .buttonStyle(.plain)
          .padding(.horizontal, 14)
          .padding(.vertical, 6)
          .background(OmiColors.purplePrimary)
          .foregroundColor(.white)
          .clipShape(RoundedRectangle(cornerRadius: 8))
        }
      }
    }
  }

  // MARK: - Advanced Subsections

  var aiSetupSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "aichat.realtimevoice") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Image(systemName: "waveform")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.textTertiary)

            Text("Voice Model")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Picker("", selection: $realtimeOmniProvider) {
              ForEach(RealtimeOmniProvider.allCases, id: \.rawValue) { p in
                Text(p.displayName).tag(p.rawValue)
              }
            }
            .pickerStyle(.menu)
            .frame(width: 200)
            .onChange(of: realtimeOmniProvider) { _, newValue in
              if newValue == RealtimeOmniProvider.auto.rawValue {
                AutoModelSelector.shared.refreshIfStale()
              }
              // The picker writes @AppStorage directly (bypassing the RealtimeOmniSettings
              // setter), so post the change ourselves — this is what re-warms the realtime
              // hub on the newly selected provider (and is a no-op for unchanged providers).
              NotificationCenter.default.post(name: .realtimeOmniSettingsDidChange, object: nil)
            }
          }

          if let p = RealtimeOmniProvider(rawValue: realtimeOmniProvider), p == .auto {
            Text("\(p.subtitle) · currently \(RealtimeOmniSettings.shared.effectiveProvider.displayName)")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          } else if let p = RealtimeOmniProvider(rawValue: realtimeOmniProvider) {
            Text(p.subtitle)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }

      settingsCard(settingId: "aichat.provider") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Image(systemName: "cpu")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.textTertiary)

            Text("AI Provider")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Picker("", selection: $chatBridgeMode) {
              ForEach(AIProvider.all) { provider in
                Text(provider.displayName).tag(provider.bridgeModeRawValue)
              }
            }
            .pickerStyle(.menu)
            .frame(width: 200)
            .onChange(of: chatBridgeMode) { _, newMode in
              if let mode = ChatProvider.BridgeMode(rawValue: newMode) {
                Task {
                  await chatProvider?.switchBridgeMode(to: mode)
                }
              }
            }
          }

          if let provider = AIProvider.from(bridgeMode: chatBridgeMode) {
            if let url = provider.attributionURL {
              Link(destination: url) {
                Text("\(provider.tagline) · \(url.host ?? "")")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)
              }
            } else {
              Text(provider.tagline)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          if chatBridgeMode == "claudeCode" && chatProvider?.isClaudeConnected == true {
            Divider()

            HStack {
              Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .scaledFont(size: 12)
              Text("Connected to Claude")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)

              Spacer()

              Button("Disconnect") {
                Task {
                  await chatProvider?.disconnectClaude()
                }
              }
              .buttonStyle(.plain)
              .scaledFont(size: 12, weight: .medium)
              .foregroundColor(.red)
            }
          }
        }
      }

      settingsCard(settingId: "aichat.workspace") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Image(systemName: "folder")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.textTertiary)

            Text("Workspace")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Button("Browse...") {
              let panel = NSOpenPanel()
              panel.canChooseFiles = false
              panel.canChooseDirectories = true
              panel.allowsMultipleSelection = false
              panel.message = "Select a project directory"
              if panel.runModal() == .OK, let url = panel.url {
                aiChatWorkingDirectory = url.path
                chatProvider?.aiChatWorkingDirectory = url.path
                Task { await chatProvider?.discoverClaudeConfig() }
                if chatProvider?.workingDirectory == nil {
                  chatProvider?.workingDirectory = url.path
                }
              }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)

            if !aiChatWorkingDirectory.isEmpty {
              Button("Clear") {
                aiChatWorkingDirectory = ""
                chatProvider?.aiChatWorkingDirectory = ""
                Task { await chatProvider?.discoverClaudeConfig() }
                chatProvider?.workingDirectory = nil
              }
              .buttonStyle(.bordered)
              .controlSize(.small)
            }
          }

          if !aiChatWorkingDirectory.isEmpty {
            Text(aiChatWorkingDirectory)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
              .truncationMode(.middle)
          } else {
            Text("No workspace set. Choose a project directory for desktop chat context.")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }

      settingsCard(settingId: "aichat.browserextension") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Image(systemName: "globe")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.textTertiary)

            Text("Browser Extension")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            if !playwrightExtensionToken.isEmpty {
              HStack(spacing: 4) {
                Circle()
                  .fill(Color.green)
                  .frame(width: 6, height: 6)
                Text("Connected")
                  .scaledFont(size: 11)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }

            Toggle("", isOn: $playwrightUseExtension)
              .toggleStyle(.switch)
              .controlSize(.small)
              .labelsHidden()
          }

          Text("Lets the AI use your Chrome browser with all your logged-in sessions.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)

          if playwrightUseExtension {
            if playwrightExtensionToken.isEmpty {
              Button(action: {
                showBrowserSetup = true
              }) {
                HStack(spacing: 6) {
                  Image(systemName: "wrench.and.screwdriver")
                    .scaledFont(size: 12)
                  Text("Set Up")
                    .scaledFont(size: 13, weight: .medium)
                }
              }
              .buttonStyle(.borderedProminent)
              .controlSize(.small)
            } else {
              HStack(spacing: 8) {
                Text("Token")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)

                Text(String(playwrightExtensionToken.prefix(8)) + "...")
                  .scaledFont(size: 12, weight: .medium)
                  .foregroundColor(OmiColors.textPrimary)
                  .font(.system(.body, design: .monospaced))

                Spacer()

                Button(action: {
                  showBrowserSetup = true
                }) {
                  HStack(spacing: 4) {
                    Image(systemName: "arrow.clockwise")
                      .scaledFont(size: 11)
                    Text("Reconfigure")
                      .scaledFont(size: 12)
                  }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                Button(action: {
                  playwrightExtensionToken = ""
                  UserDefaults.standard.set("", forKey: "playwrightExtensionToken")
                }) {
                  HStack(spacing: 4) {
                    Image(systemName: "xmark")
                      .scaledFont(size: 11)
                    Text("Reset")
                      .scaledFont(size: 12)
                  }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
              }
            }
          }
        }
      }

      settingsCard(settingId: "aichat.devmode") {
        VStack(alignment: .leading, spacing: 12) {
          HStack {
            Image(systemName: "hammer")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.textTertiary)

            Text("Dev Mode")
              .scaledFont(size: 15, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Toggle("", isOn: $devModeEnabled)
              .toggleStyle(.switch)
              .controlSize(.small)
              .labelsHidden()
              .onChange(of: devModeEnabled) { _, newValue in
                AnalyticsManager.shared.settingToggled(setting: "dev_mode", enabled: newValue)
              }
          }

          Text("Let the AI modify the app's source code, rebuild it, and add custom features.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
        }
      }
    }
  }

  var profileAndStatsSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.profileandstats") {
        VStack(alignment: .leading, spacing: 12) {
          HStack(spacing: 12) {
            Image(systemName: showProfileAndStats ? "eye.slash" : "eye")
              .scaledFont(size: 15)
              .foregroundColor(OmiColors.purplePrimary)

            VStack(alignment: .leading, spacing: 4) {
              Text("Profile and Stats")
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
              Text("Keep the generated profile and usage stats hidden until you need them.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Button(showProfileAndStats ? "Hide" : "Show") {
              withAnimation(.easeInOut(duration: 0.2)) {
                showProfileAndStats.toggle()
              }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
          }
        }
      }

      if showProfileAndStats {
        aiUserProfileSubsection
        writingVoiceSubsection
        statsSubsection
      }
    }
  }

  var aiUserProfileSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.aiuserprofile") {
        VStack(alignment: .leading, spacing: 16) {
          HStack(spacing: 10) {
            Image(systemName: "brain")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            Text("AI User Profile")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            if isGeneratingAIProfile {
              ProgressView()
                .controlSize(.small)
            } else {
              Button(action: {
                regenerateAIProfile()
              }) {
                Text(aiProfileText == nil ? "Generate Now" : "Regenerate")
                  .scaledFont(size: 12)
              }
              .buttonStyle(.bordered)
              .controlSize(.small)
            }
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          if let text = aiProfileText {
            if isEditingAIProfile {
              TextEditor(text: $aiProfileEditText)
                .scaledFont(size: 13, design: .monospaced)
                .foregroundColor(OmiColors.textSecondary)
                .scrollContentBackground(.hidden)
                .frame(maxHeight: 200)

              HStack {
                Button("Cancel") {
                  isEditingAIProfile = false
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                Button("Save") {
                  if let id = aiProfileId {
                    Task {
                      let success = await AIUserProfileService.shared.updateProfileText(
                        id: id, newText: aiProfileEditText
                      )
                      if success {
                        aiProfileText = aiProfileEditText
                      }
                      isEditingAIProfile = false
                    }
                  }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)

                Spacer()
              }
            } else {
              ScrollView {
                Text(text)
                  .scaledFont(size: 13, design: .monospaced)
                  .foregroundColor(OmiColors.textSecondary)
                  .textSelection(.enabled)
                  .if_available_writingToolsNone()
                  .frame(maxWidth: .infinity, alignment: .leading)
              }
              .frame(maxHeight: 200)

              HStack {
                if let date = aiProfileGeneratedAt {
                  Text("Last updated: \(date.formatted(.relative(presentation: .named)))")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                if aiProfileDataSourcesUsed > 0 {
                  Text("Data sources: \(aiProfileDataSourcesUsed) items")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                }

                Button(action: {
                  aiProfileEditText = text
                  isEditingAIProfile = true
                }) {
                  Image(systemName: "pencil")
                    .scaledFont(size: 11)
                }
                .buttonStyle(.borderless)
                .help("Edit profile")

                Button(action: {
                  deleteCurrentAIProfile()
                }) {
                  Image(systemName: "trash")
                    .scaledFont(size: 11)
                    .foregroundColor(.red.opacity(0.7))
                }
                .buttonStyle(.borderless)
                .help("Delete this profile")
              }
            }
          } else if !isGeneratingAIProfile {
            Text(
              "Your AI user profile will be generated automatically on next launch, or click \"Generate Now\" to create it now."
            )
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)
          } else {
            HStack {
              Spacer()
              VStack(spacing: 8) {
                ProgressView()
                Text("Generating profile...")
                  .scaledFont(size: 13)
                  .foregroundColor(OmiColors.textTertiary)
              }
              Spacer()
            }
            .padding(.vertical, 20)
          }
        }
      }
    }
    .task {
      // Try loading immediately (covers all restarts after first generation)
      if let profile = await AIUserProfileService.shared.getLatestProfile() {
        aiProfileId = profile.id
        aiProfileText = profile.profileText
        aiProfileGeneratedAt = profile.generatedAt
        aiProfileDataSourcesUsed = profile.dataSourcesUsed
        return
      }
      // No profile yet — first-ever generation may be in progress, poll briefly
      for _ in 0..<6 {
        try? await Task.sleep(nanoseconds: 5_000_000_000)
        if let profile = await AIUserProfileService.shared.getLatestProfile() {
          aiProfileId = profile.id
          aiProfileText = profile.profileText
          aiProfileGeneratedAt = profile.generatedAt
          aiProfileDataSourcesUsed = profile.dataSourcesUsed
          return
        }
      }
    }
  }

  var writingVoiceSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.writingvoice") {
        VStack(alignment: .leading, spacing: 16) {
          HStack(spacing: 10) {
            Image(systemName: "text.bubble")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.textPrimary)

            Text("Writing Voice")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            if isGeneratingToneGuide {
              ProgressView()
                .controlSize(.small)
            } else {
              Button(action: {
                regenerateToneGuideAction()
              }) {
                Text(toneGuideText == nil ? "Generate Now" : "Regenerate")
                  .scaledFont(size: 12)
              }
              .buttonStyle(.bordered)
              .controlSize(.small)
            }
          }

          Text("A tone & style guide Omi learns from your real messages, and uses to draft replies that sound like you.")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)

          Divider()
            .background(OmiColors.backgroundQuaternary)

          if let text = toneGuideText, !text.isEmpty {
            ScrollView {
              Text(text)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .textSelection(.enabled)
                .if_available_writingToolsNone()
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 260)

            HStack {
              if let date = toneGuideGeneratedAt {
                Text("Updated \(date.formatted(.relative(presentation: .named)))")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)
              }
              Spacer()
              if toneGuideSampleCount > 0 {
                Text("From \(toneGuideSampleCount) messages")
                  .scaledFont(size: 12)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }
          } else if !isGeneratingToneGuide {
            Text(
              "Sync your messages (iMessage, Telegram, or WhatsApp) and Omi will build your writing voice automatically, or click \"Generate Now\"."
            )
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
          } else {
            HStack {
              Spacer()
              VStack(spacing: 8) {
                ProgressView()
                Text("Learning your voice...")
                  .scaledFont(size: 13)
                  .foregroundColor(OmiColors.textTertiary)
              }
              Spacer()
            }
            .padding(.vertical, 20)
          }
        }
      }
    }
    .task {
      await loadToneGuide()
    }
  }

  private func parseToneGuideDate(_ value: String?) -> Date? {
    guard let value = value else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: value) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.date(from: value)
  }

  func loadToneGuide() async {
    guard let guide = try? await APIClient.shared.getToneGuide() else { return }
    toneGuideText = guide.guideText
    toneGuideGeneratedAt = parseToneGuideDate(guide.generatedAt)
    toneGuideSampleCount = guide.sampleCount ?? 0
  }

  func regenerateToneGuideAction() {
    isGeneratingToneGuide = true
    Task {
      defer { isGeneratingToneGuide = false }
      guard let guide = try? await APIClient.shared.regenerateToneGuide() else { return }
      toneGuideText = guide.guideText
      toneGuideGeneratedAt = parseToneGuideDate(guide.generatedAt)
      toneGuideSampleCount = guide.sampleCount ?? 0
    }
  }

  var statsSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.stats") {
        VStack(alignment: .leading, spacing: 16) {
          HStack(spacing: 10) {
            Image(systemName: "chart.bar")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            Text("Your Stats")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          if let stats = advancedStats {
            statRow(label: "Conversations", value: stats.conversations)
            statRow(label: "Apps Installed", value: stats.appsInstalled)
            if isLoadingChatMessages {
              HStack {
                Text("AI Chat Messages")
                  .scaledFont(size: 14)
                  .foregroundColor(OmiColors.textSecondary)
                Spacer()
                ProgressView()
                  .controlSize(.mini)
              }
            } else if let count = chatMessageCount {
              statRow(label: "AI Chat Messages", value: count)
            }
            statRow(label: "Screenshots", value: stats.screenshotsTotal)
            statRow(label: "Focus Sessions", value: stats.focusSessions)
            statRow(label: "Tasks (To Do)", value: stats.tasksTodo)
            statRow(label: "Tasks (Done)", value: stats.tasksDone)
            statRow(label: "Tasks (Removed)", value: stats.tasksDeleted)
            statRow(label: "Goals", value: stats.goalsCount)
            statRow(label: "Memories", value: stats.memoriesTotal)
          } else if isLoadingStats {
            statRowLoading(label: "Conversations")
            statRowLoading(label: "Apps Installed")
            statRowLoading(label: "AI Chat Messages")
            statRowLoading(label: "Screenshots")
            statRowLoading(label: "Focus Sessions")
            statRowLoading(label: "Tasks (To Do)")
            statRowLoading(label: "Tasks (Done)")
            statRowLoading(label: "Tasks (Removed)")
            statRowLoading(label: "Goals")
            statRowLoading(label: "Memories")
          } else {
            Text("Unable to load stats")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }
    }
    .task {
      await loadAdvancedStats()
    }
    .task {
      await loadChatMessageCount()
    }
  }

  var featureTiersSubsection: some View {
    VStack(spacing: 20) {
      settingsCard(settingId: "advanced.featuretiers") {
        VStack(alignment: .leading, spacing: 16) {
          HStack(spacing: 10) {
            Image(systemName: "lock.shield")
              .scaledFont(size: 16)
              .foregroundColor(OmiColors.purplePrimary)

            Text("Feature Tiers")
              .scaledFont(size: 15, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          // Tier picker — radio-style selector
          VStack(alignment: .leading, spacing: 6) {
            tierPickerRow(tier: 0, label: "Show All Features", subtitle: "Unlock everything")
            tierPickerRow(tier: 1, label: "Tier 1", subtitle: "Conversations + Rewind")
            tierPickerRow(tier: 2, label: "Tier 2", subtitle: "+ Memories (100 memories)")
            tierPickerRow(tier: 3, label: "Tier 3", subtitle: "+ Tasks (100 tasks)")
            tierPickerRow(tier: 4, label: "Tier 4", subtitle: "+ AI Chat (100 conversations)")
            tierPickerRow(
              tier: 5, label: "Tier 5", subtitle: "+ Home (200 convos + 2K screenshots)")
            tierPickerRow(tier: 6, label: "Tier 6", subtitle: "+ Apps (300 conversations)")
          }

          if currentTierLevel > 0 {
            Divider()
              .background(OmiColors.backgroundQuaternary)

            Text("Progress")
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)

            // Tier 1 — always unlocked
            tierFeatureRow(
              tier: 1, name: "Conversations + Rewind",
              requirement: "Always unlocked",
              progress: nil, unlocked: true
            )

            // Tier 2 — 100 memories
            tierFeatureRow(
              tier: 2, name: "Memories",
              requirement: "100 memories",
              progress: advancedStats.map { "\($0.memoriesTotal) / 100" },
              unlocked: currentTierLevel >= 2
            )

            // Tier 3 — 100 tasks
            tierFeatureRow(
              tier: 3, name: "Tasks",
              requirement: "100 tasks (todo + done)",
              progress: advancedStats.map { "\($0.tasksTodo + $0.tasksDone) / 100" },
              unlocked: currentTierLevel >= 3
            )

            // Tier 4 — 100 conversations
            tierFeatureRow(
              tier: 4, name: "AI Chat",
              requirement: "100 conversations",
              progress: advancedStats.map { "\($0.conversations) / 100" },
              unlocked: currentTierLevel >= 4
            )

            // Tier 5 — 200 conversations + 2,000 screenshots
            tierFeatureRow(
              tier: 5, name: "Home",
              requirement: "200 conversations + 2K screenshots",
              progress: advancedStats.map {
                "\($0.conversations) / 200 convos, \($0.screenshotsTotal) / 2,000 screenshots"
              },
              unlocked: currentTierLevel >= 5
            )

            // Tier 6 — 300 conversations
            tierFeatureRow(
              tier: 6, name: "Apps",
              requirement: "300 conversations",
              progress: advancedStats.map { "\($0.conversations) / 300" },
              unlocked: currentTierLevel >= 6
            )
          }
        }
      }
    }
  }

}
