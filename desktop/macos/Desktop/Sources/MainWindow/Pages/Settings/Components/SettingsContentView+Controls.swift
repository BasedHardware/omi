import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var floatingBarTypedVoiceAnswersBinding: Binding<Bool> {
    Binding(
      get: { shortcutSettings.floatingBarTypedQuestionVoiceAnswersEnabled },
      set: { newValue in
        shortcutSettings.floatingBarTypedQuestionVoiceAnswersEnabled = newValue
      }
    )
  }

  func voiceSpeedSlider(settingId: String) -> some View {
    let steps = ShortcutSettings.voiceSpeedSteps
    let currentSpeed = shortcutSettings.voicePlaybackSpeed
    let currentIndex =
      steps.enumerated().min(by: { abs($0.element - currentSpeed) < abs($1.element - currentSpeed) }
      )?.offset ?? 3

    return settingsCard(settingId: settingId) {
      VStack(spacing: OmiSpacing.lg) {
        HStack {
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(ShortcutSettings.voiceSpeedLabel(for: currentSpeed))
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Voice playback speed")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
          }
          Spacer()
          Text("\(String(format: "%.1f", currentSpeed))×")
            .font(.system(size: 22, weight: .bold, design: .rounded))
            .foregroundColor(OmiColors.accent)
            .frame(width: 52, height: 52)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
                .fill(OmiColors.accent.opacity(0.15))
            )
        }

        VStack(spacing: OmiSpacing.xs) {
          // Stepped slider
          GeometryReader { geo in
            let trackWidth = geo.size.width
            let segmentCount = CGFloat(steps.count - 1)

            ZStack(alignment: .leading) {
              // Track background
              RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                .fill(OmiColors.backgroundQuaternary)
                .frame(height: 6)

              // Filled track
              RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                .fill(OmiColors.accent)
                .frame(width: trackWidth * CGFloat(currentIndex) / segmentCount, height: 6)

              // Step dots
              ForEach(0..<steps.count, id: \.self) { i in
                Circle()
                  .fill(
                    i <= currentIndex ? OmiColors.accent : OmiColors.backgroundQuaternary
                  )
                  .frame(width: 12, height: 12)
                  .position(
                    x: trackWidth * CGFloat(i) / segmentCount,
                    y: geo.size.height / 2
                  )
              }

              // Thumb
              Circle()
                .fill(Color.white)
                .frame(width: 22, height: 22)
                .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                .position(
                  x: trackWidth * CGFloat(currentIndex) / segmentCount,
                  y: geo.size.height / 2
                )
                .gesture(
                  DragGesture(minimumDistance: 0)
                    .onChanged { value in
                      let fraction = max(0, min(1, value.location.x / trackWidth))
                      let nearestIndex = Int(round(fraction * segmentCount))
                      let clamped = max(0, min(steps.count - 1, nearestIndex))
                      shortcutSettings.voicePlaybackSpeed = steps[clamped]
                    }
                )
            }
          }
          .frame(height: 22)

          HStack {
            Text("Slow")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
            Spacer()
            Text("Max")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }
    }
  }

  /// Stepped slider for `notifications.frequency` matching the voice-speed slider
  /// pattern. Six positions: Off / Minimal / Low / Balanced / High / Maximum.
  /// Sits inside the existing Notifications card, so it does not wrap itself in
  /// another `settingsCard` — it just applies the highlight modifier directly.
  func notificationFrequencySlider(settingId: String) -> some View {
    let stepCount = frequencyOptions.count  // 6
    let segmentCount = CGFloat(stepCount - 1)
    let currentIndex = max(0, min(stepCount - 1, notificationFrequency))
    let currentLabel = frequencyOptions[currentIndex].1

    let body = VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(alignment: .center) {
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text("Frequency")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textSecondary)
          Text("How often to receive notifications")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }
        Spacer()
        Text(currentLabel)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.accent)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
              .fill(OmiColors.accent.opacity(0.15))
          )
      }

      GeometryReader { geo in
        let trackWidth = geo.size.width

        ZStack(alignment: .leading) {
          RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
            .fill(OmiColors.backgroundQuaternary)
            .frame(height: 6)

          RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
            .fill(OmiColors.accent)
            .frame(width: trackWidth * CGFloat(currentIndex) / segmentCount, height: 6)

          ForEach(0..<stepCount, id: \.self) { i in
            Circle()
              .fill(
                i <= currentIndex ? OmiColors.accent : OmiColors.backgroundQuaternary
              )
              .frame(width: 12, height: 12)
              .position(
                x: trackWidth * CGFloat(i) / segmentCount,
                y: geo.size.height / 2
              )
          }

          Circle()
            .fill(Color.white)
            .frame(width: 22, height: 22)
            .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
            .position(
              x: trackWidth * CGFloat(currentIndex) / segmentCount,
              y: geo.size.height / 2
            )
            .gesture(
              DragGesture(minimumDistance: 0)
                .onChanged { value in
                  let fraction = max(0, min(1, value.location.x / trackWidth))
                  let nearestIndex = Int(round(fraction * segmentCount))
                  let clamped = max(0, min(stepCount - 1, nearestIndex))
                  if clamped != notificationFrequency {
                    notificationFrequency = clamped
                    updateNotificationSettings(frequency: clamped)
                  }
                }
            )
        }
      }
      .frame(height: 22)

      HStack {
        Text(frequencyOptions.first?.1 ?? "Off")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
        Spacer()
        Text(frequencyOptions.last?.1 ?? "Maximum")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }
    }

    return body.modifier(
      SettingHighlightModifier(
        settingId: settingId, highlightedSettingId: $highlightedSettingId))
  }

  func tierPickerRow(tier: Int, label: String, subtitle: String) -> some View {
    let isSelected = currentTierLevel == tier
    return Button(action: {
      TierManager.shared.userDidSetTier(tier)
    }) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: isSelected ? "largecircle.fill.circle" : "circle")
          .scaledFont(size: OmiType.subheading)
          .foregroundColor(isSelected ? OmiColors.accent : OmiColors.textTertiary)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(label)
            .scaledFont(size: OmiType.body, weight: isSelected ? .medium : .regular)
            .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)

          Text(subtitle)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()
      }
      .padding(.vertical, OmiSpacing.xs)
      .padding(.horizontal, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isSelected ? OmiColors.accent.opacity(0.1) : Color.clear)
      )
    }
    .buttonStyle(.plain)
  }

  func tierFeatureRow(
    tier: Int, name: String, requirement: String, progress: String?, unlocked: Bool
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      HStack {
        Text("Tier \(tier)")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(unlocked ? OmiColors.accent : OmiColors.textTertiary)
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.hairline)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
              .fill(unlocked ? OmiColors.accent.opacity(0.15) : OmiColors.backgroundTertiary)
          )

        Text(name)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(unlocked ? OmiColors.textPrimary : OmiColors.textTertiary)

        Spacer()

        if unlocked {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.body)
            .foregroundColor(.green)
        } else {
          Image(systemName: "lock.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }
      }

      HStack(spacing: OmiSpacing.sm) {
        Text(requirement)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)

        if let progress = progress, !unlocked {
          Text("(\(progress))")
            .scaledMonospacedDigitFont(size: 12)
            .foregroundColor(OmiColors.textTertiary.opacity(0.7))
        }
      }
    }
    .padding(.vertical, OmiSpacing.xxs)
  }

  func statRow(label: String, value: Int) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)

      Spacer()

      Text(formatNumber(value))
        .scaledMonospacedDigitFont(size: 14, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)
    }
  }

  func statRowLoading(label: String) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)

      Spacer()

      ProgressView()
        .controlSize(.mini)
    }
  }

  func formatNumber(_ n: Int) -> String {
    let formatter = NumberFormatter()
    formatter.numberStyle = .decimal
    return formatter.string(from: NSNumber(value: n)) ?? "\(n)"
  }

  func loadAdvancedStats() async {
    isLoadingStats = true
    defer { isLoadingStats = false }

    do {
      async let conversationsCount = APIClient.shared.getConversationsCount()
      async let installedApps = APIClient.shared.searchApps(installedOnly: true)
      async let focusCount = ProactiveStorage.shared.getTotalFocusSessionCount()
      async let filterCounts = ActionItemStorage.shared.getFilterCounts()
      async let goals = APIClient.shared.getGoals()
      async let memoryStats = MemoryStorage.shared.getStats()

      let cc = try await conversationsCount
      let ia = try await installedApps
      let fc = try await focusCount
      let filters = try await filterCounts
      let g = try await goals
      let ms = try await memoryStats

      let screenshotCount: Int
      do {
        screenshotCount = try await RewindDatabase.shared.getScreenshotCount()
      } catch {
        screenshotCount = 0
      }

      advancedStats = UserStats(
        conversations: cc,
        appsInstalled: ia.count,
        screenshotsTotal: screenshotCount,
        focusSessions: fc,
        tasksTodo: filters.todo,
        tasksDone: filters.done,
        tasksDeleted: filters.deleted,
        goalsCount: g.count,
        memoriesTotal: ms.total
      )
    } catch {
      print("SETTINGS: Failed to load advanced stats: \(error)")
    }
  }

  func loadChatMessageCount() async {
    isLoadingChatMessages = true
    defer { isLoadingChatMessages = false }

    do {
      chatMessageCount = try await APIClient.shared.getChatMessageCount()
    } catch {
      chatMessageCount = 0
    }
  }

  // MARK: - About Section

  var aboutSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "about.version") {
        VStack(spacing: OmiSpacing.lg) {
          // App info
          HStack(spacing: OmiSpacing.lg) {
            if let logoURL = Bundle.resourceBundle.url(
              forResource: "herologo", withExtension: "png"),
              let logoImage = NSImage(contentsOf: logoURL)
            {
              Image(nsImage: logoImage)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 48, height: 48)
            }

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              HStack(spacing: OmiSpacing.xs) {
                Text("omi")
                  .scaledFont(size: OmiType.heading, weight: .bold)
                  .foregroundColor(OmiColors.textPrimary)

                if !updaterViewModel.activeChannelLabel.isEmpty {
                  Text("(\(updaterViewModel.activeChannelLabel))")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.accent)
                }
              }

              Text("Version \(updaterViewModel.currentVersion) (\(updaterViewModel.buildNumber))")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
                .textSelection(.enabled)
            }

            Spacer()
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          // Links
          linkRow(title: "What's New", url: AppBuild.changelogURLString)
          linkRow(title: "Visit Website", url: "https://omi.me")
          linkRow(title: "Help Center", url: "https://help.omi.me")
          Button(action: {
            selectedSection = .privacy
          }) {
            HStack {
              Text("Privacy Policy")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textSecondary)

              Spacer()

              Image(systemName: "arrow.right")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }
          }
          .buttonStyle(.plain)
          linkRow(title: "Terms of Service", url: "https://omi.me/terms")
        }
      }

      // Software Updates
      settingsCard(settingId: "about.updates") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "arrow.triangle.2.circlepath")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textSecondary)

            Text("Software Updates")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Button("Check Now") {
              updaterViewModel.checkForUpdates()
            }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
            .disabled(!updaterViewModel.canCheckForUpdates)
            .help(
              updaterViewModel.canCheckForUpdates
                ? "Check for app updates" : "Already checking for updates…")
          }

          if let lastCheck = updaterViewModel.lastUpdateCheckDate {
            Text("Last checked: \(lastCheck, style: .relative) ago")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }

          if let failure = updaterViewModel.lastUpdateFailure {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack(alignment: .top, spacing: OmiSpacing.sm) {
                Image(systemName: "exclamationmark.triangle.fill")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.warning)

                VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                  Text("Update Needs Attention")
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                  Text(failure.userMessage)
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                }
              }

              HStack(spacing: OmiSpacing.sm) {
                if failure.isRecoverableLaunchLocation {
                  Button("Open Applications") {
                    NSWorkspace.shared.open(
                      URL(fileURLWithPath: "/Applications", isDirectory: true))
                  }
                  .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
                }

                Button("Download Latest") {
                  openURLInDefaultBrowser(AppBuild.manualDownloadURL)
                }
                .buttonStyle(OmiButtonStyle(.secondary, size: .compact))

                Button("Dismiss") {
                  updaterViewModel.lastUpdateFailure = nil
                }
                .buttonStyle(.borderless)
              }
            }
            .padding(OmiSpacing.md)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(OmiChrome.elementRadius)
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          settingRow(
            title: "Automatic Updates",
            subtitle: "Check for updates automatically in the background",
            settingId: "about.autoupdates"
          ) {
            Toggle("", isOn: $updaterViewModel.automaticallyChecksForUpdates)
              .toggleStyle(OmiToggleStyle())
              .labelsHidden()
              .disabled(updaterViewModel.usesManagedUpdatePolicy || AnalyticsManager.isDevBuild)
          }

          if updaterViewModel.automaticallyChecksForUpdates {
            settingRow(
              title: "Auto-Install Updates",
              subtitle: "Automatically download and install updates when available",
              settingId: "about.autoinstall"
            ) {
              Toggle("", isOn: $updaterViewModel.automaticallyDownloadsUpdates)
                .toggleStyle(OmiToggleStyle())
                .labelsHidden()
                .disabled(updaterViewModel.usesManagedUpdatePolicy || AnalyticsManager.isDevBuild)
            }
          }

          if updaterViewModel.usesManagedUpdatePolicy {
            Text("Release builds always auto-check and auto-install updates in the background.")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          } else if AnalyticsManager.isDevBuild {
            Text(
              "Development builds keep automatic installation disabled to avoid replacing the local app."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
          }

          Divider()
            .background(OmiColors.backgroundQuaternary)

          settingRow(
            title: "Update Channel", subtitle: updaterViewModel.updateChannel.description,
            settingId: "about.channel"
          ) {
            Picker(
              "",
              selection: Binding(
                get: { updaterViewModel.updateChannel },
                set: { newChannel in
                  // Switching beta → stable with a newer build: confirm first
                  if updaterViewModel.updateChannel == .beta && newChannel == .stable
                    && updaterViewModel.isDowngradeToStable
                  {
                    showDowngradeAlert = true
                  } else {
                    updaterViewModel.updateChannel = newChannel
                  }
                }
              )
            ) {
              ForEach(UpdateChannel.allCases, id: \.self) { channel in
                Text(channel.displayName).tag(channel)
              }
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .frame(width: 100)
          }
        }
      }
      .alert("Switch to Stable Channel?", isPresented: $showDowngradeAlert) {
        Button("Stay on Beta", role: .cancel) {}
        Button("Switch to Stable") {
          updaterViewModel.updateChannel = .stable
          if let url = URL(string: "https://macos.omi.me") {
            NSWorkspace.shared.open(url)
          }
        }
      } message: {
        let stableVersion = updaterViewModel.latestStableVersionString ?? "an older version"
        Text(
          "You're on a newer beta build (\(updaterViewModel.currentVersion)). The latest stable release is \(stableVersion).\n\nSwitching to Stable means you won't receive new updates until a stable release surpasses your current version. You can also download the stable version now."
        )
      }

      settingsCard(settingId: "about.reportissue") {
        HStack(spacing: OmiSpacing.lg) {
          Image(systemName: "exclamationmark.bubble.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textSecondary)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Report an Issue")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Text("Help us improve omi")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          Button("Report") {
            FeedbackWindow.show(userEmail: AuthState.shared.userEmail)
          }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        }
      }
    }
  }

  // MARK: - Helper Views

  func fontShortcutRow(label: String, keys: String) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textTertiary)
      Spacer()
      Text(keys)
        .scaledMonospacedFont(size: 13, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.hairline)
        .background(OmiColors.backgroundTertiary.opacity(0.8))
        .cornerRadius(OmiChrome.badgeRadius)
    }
  }

  func settingsCard<Content: View>(
    settingId: String? = nil, @ViewBuilder content: () -> Content
  ) -> some View {
    let card = content()
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(OmiSpacing.xl)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(OmiColors.backgroundTertiary.opacity(0.5))
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(OmiColors.backgroundQuaternary.opacity(0.3), lineWidth: 1)
          )
      )
    return Group {
      if let settingId = settingId {
        card.modifier(
          SettingHighlightModifier(
            settingId: settingId, highlightedSettingId: $highlightedSettingId))
      } else {
        card
      }
    }
  }

  func settingRow<Content: View>(
    title: String, subtitle: String, settingId: String? = nil, @ViewBuilder control: () -> Content
  ) -> some View {
    let row = HStack {
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
        Text(subtitle)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()

      control()
    }
    return Group {
      if let settingId = settingId {
        row.modifier(
          SettingHighlightModifier(
            settingId: settingId, highlightedSettingId: $highlightedSettingId))
      } else {
        row
      }
    }
  }

  func linkRow(title: String, url: String) -> some View {
    Button(action: {
      if let url = URL(string: url) {
        NSWorkspace.shared.open(url)
      }
    }) {
      HStack {
        Text(title)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)

        Spacer()

        Image(systemName: "arrow.up.right")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }
    }
    .buttonStyle(.plain)
  }

  func trackingItem(_ text: String) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Circle()
        .fill(OmiColors.textTertiary.opacity(0.5))
        .frame(width: 4, height: 4)

      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textTertiary)
    }
  }

  func privacyBullet(_ text: String) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "checkmark")
        .scaledFont(size: OmiType.micro, weight: .bold)
        .foregroundColor(.green)

      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textSecondary)
    }
  }

  func privacyToggleRow(
    icon: String,
    title: String,
    subtitle: String,
    isOn: Binding<Bool>,
    onChange: @escaping (Bool) -> Void
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 20, alignment: .leading)

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(title)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)

          Text(subtitle)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        }

        Spacer(minLength: 12)

        Toggle("", isOn: isOn)
          .toggleStyle(OmiToggleStyle())
          .labelsHidden()
          .controlSize(.small)
          .onChange(of: isOn.wrappedValue) { _, newValue in
            onChange(newValue)
          }
      }
    }
  }

}
