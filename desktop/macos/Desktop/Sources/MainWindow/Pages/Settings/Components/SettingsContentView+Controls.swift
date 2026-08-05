import AppKit
import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

enum SettingsControlMetrics {
  static let steppedSliderThumbDiameter: CGFloat = 22

  static func steppedSliderInset(in containerWidth: CGFloat) -> CGFloat {
    min(steppedSliderThumbDiameter / 2, max(0, containerWidth / 2))
  }

  static func steppedSliderTrackWidth(in containerWidth: CGFloat) -> CGFloat {
    max(0, containerWidth - (2 * steppedSliderInset(in: containerWidth)))
  }

  static func steppedSliderPosition(index: Int, stepCount: Int, containerWidth: CGFloat) -> CGFloat {
    let inset = steppedSliderInset(in: containerWidth)
    guard stepCount > 1 else { return inset }

    let clampedIndex = max(0, min(stepCount - 1, index))
    let fraction = CGFloat(clampedIndex) / CGFloat(stepCount - 1)
    return inset + (steppedSliderTrackWidth(in: containerWidth) * fraction)
  }

  static func steppedSliderIndex(locationX: CGFloat, stepCount: Int, containerWidth: CGFloat) -> Int {
    let trackWidth = steppedSliderTrackWidth(in: containerWidth)
    guard stepCount > 1, trackWidth > 0 else { return 0 }

    let fraction = max(0, min(1, (locationX - steppedSliderInset(in: containerWidth)) / trackWidth))
    return Int(round(fraction * CGFloat(stepCount - 1)))
  }

  static func dailySummaryDate(forHour hour: Int, referenceDate: Date, calendar: Calendar = .current) -> Date {
    let normalizedHour = max(0, min(23, hour))
    return calendar.date(bySettingHour: normalizedHour, minute: 0, second: 0, of: referenceDate)
      ?? referenceDate
  }

  static func dailySummaryHour(from date: Date, calendar: Calendar = .current) -> Int {
    calendar.component(.hour, from: date)
  }
}

struct SettingsMenuPicker<SelectionValue: Hashable, Content: View>: View {
  @Binding private var selection: SelectionValue
  private let content: Content

  init(selection: Binding<SelectionValue>, @ViewBuilder content: () -> Content) {
    _selection = selection
    self.content = content()
  }

  var body: some View {
    Picker("", selection: $selection) {
      content
    }
    .pickerStyle(.menu)
    .labelsHidden()
    .fixedSize()
  }
}

private struct SettingsTextInputStyle: ViewModifier {
  func body(content: Content) -> some View {
    content
      .textFieldStyle(.plain)
      .scaledFont(size: OmiType.body)
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.sm)
      // A well, not a card: `Ink.hairline` is the outline of something you type into, which is a
      // different job from the rule between two blocks — see `Ink.hairline` vs `Ink.separator`.
      .settingsGlassWell(radius: SettingsGlassMetrics.controlRadius)
  }
}

extension View {
  func settingsTextInputStyle() -> some View {
    modifier(SettingsTextInputStyle())
  }
}

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
              .foregroundColor(Ink.primary)
            Text("Voice playback speed")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }
          Spacer()
          // `Ink.primary`, for the reason the frequency readout below is: the accent is a light hue
          // and a number set in it on this panel is the hardest thing on the row to read.
          Text("\(String(format: "%.1f", currentSpeed))×")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(Ink.primary)
        }

        VStack(spacing: OmiSpacing.xs) {
          // Stepped slider
          GeometryReader { geo in
            let segmentCount = CGFloat(steps.count - 1)
            let trackWidth = SettingsControlMetrics.steppedSliderTrackWidth(in: geo.size.width)
            let trackInset = SettingsControlMetrics.steppedSliderInset(in: geo.size.width)

            ZStack(alignment: .leading) {
              // Track background
              RoundedRectangle(cornerRadius: OmiChrome.stripRadius, style: .continuous)
                .fill(Ink.hairline)
                .frame(width: trackWidth, height: 6)
                .offset(x: trackInset)

              // Filled track
              RoundedRectangle(cornerRadius: OmiChrome.stripRadius, style: .continuous)
                .fill(Ink.primary)
                .frame(width: trackWidth * CGFloat(currentIndex) / segmentCount, height: 6)
                .offset(x: trackInset)

              // Step dots
              ForEach(0..<steps.count, id: \.self) { i in
                Circle()
                  .fill(
                    i <= currentIndex ? Ink.accent : Ink.hairline
                  )
                  .frame(width: 12, height: 12)
                  .position(
                    x: SettingsControlMetrics.steppedSliderPosition(
                      index: i, stepCount: steps.count, containerWidth: geo.size.width),
                    y: geo.size.height / 2
                  )
              }

              // Thumb
              Circle()
                .fill(Ink.surface)
                .frame(width: 22, height: 22)
                .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                .position(
                  x: SettingsControlMetrics.steppedSliderPosition(
                    index: currentIndex, stepCount: steps.count, containerWidth: geo.size.width),
                  y: geo.size.height / 2
                )
                .gesture(
                  DragGesture(minimumDistance: 0, coordinateSpace: .named("voiceSpeedSlider"))
                    .onChanged { value in
                      let clamped = SettingsControlMetrics.steppedSliderIndex(
                        locationX: value.location.x, stepCount: steps.count,
                        containerWidth: geo.size.width)
                      if shortcutSettings.voicePlaybackSpeed != steps[clamped] {
                        performStepHaptic()
                        shortcutSettings.voicePlaybackSpeed = steps[clamped]
                      }
                    }
                )
            }
          }
          .coordinateSpace(name: "voiceSpeedSlider")
          .frame(height: 22)

          HStack {
            Text("Slow")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
            Spacer()
            Text("Max")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
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
            .foregroundColor(Ink.secondary)
          Text("How often to receive notifications")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        Spacer()
        // The value readout, in the same shape `SettingsStatusChip` settled on: the tint is the
        // ground, the word is `Ink.primary`. Set *in* the accent over 15% of the accent it measured
        // about 2.8:1 on this panel — the number a slider exists to report was the faintest thing on
        // the row.
        Text(currentLabel)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
              .fill(Ink.accent.opacity(0.16))
          )
      }

      GeometryReader { geo in
        let trackWidth = SettingsControlMetrics.steppedSliderTrackWidth(in: geo.size.width)
        let trackInset = SettingsControlMetrics.steppedSliderInset(in: geo.size.width)

        ZStack(alignment: .leading) {
          RoundedRectangle(cornerRadius: OmiChrome.stripRadius, style: .continuous)
            .fill(Ink.hairline)
            .frame(width: trackWidth, height: 6)
            .offset(x: trackInset)

          RoundedRectangle(cornerRadius: OmiChrome.stripRadius, style: .continuous)
            .fill(Ink.primary)
            .frame(width: trackWidth * CGFloat(currentIndex) / segmentCount, height: 6)
            .offset(x: trackInset)

          ForEach(0..<stepCount, id: \.self) { i in
            Circle()
              .fill(
                i <= currentIndex ? Ink.accent : Ink.hairline
              )
              .frame(width: 12, height: 12)
              .position(
                x: SettingsControlMetrics.steppedSliderPosition(
                  index: i, stepCount: stepCount, containerWidth: geo.size.width),
                y: geo.size.height / 2
              )
          }

          Circle()
            .fill(Ink.surface)
            .frame(width: 22, height: 22)
            .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
            .position(
              x: SettingsControlMetrics.steppedSliderPosition(
                index: currentIndex, stepCount: stepCount, containerWidth: geo.size.width),
              y: geo.size.height / 2
            )
            .gesture(
              DragGesture(minimumDistance: 0, coordinateSpace: .named("notificationFrequencySlider"))
                .onChanged { value in
                  let clamped = SettingsControlMetrics.steppedSliderIndex(
                    locationX: value.location.x, stepCount: stepCount, containerWidth: geo.size.width)
                  if clamped != notificationFrequency {
                    performStepHaptic()
                    notificationFrequency = clamped
                    updateNotificationSettings(frequency: clamped)
                  }
                }
            )
        }
      }
      .coordinateSpace(name: "notificationFrequencySlider")
      .frame(height: 22)

      HStack {
        Text(frequencyOptions.first?.1 ?? "Off")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        Spacer()
        Text(frequencyOptions.last?.1 ?? "Maximum")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
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
          .foregroundColor(isSelected ? Ink.accent : Ink.secondary)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(label)
            .scaledFont(size: OmiType.body, weight: isSelected ? .medium : .regular)
            .foregroundColor(isSelected ? Ink.primary : Ink.secondary)

          Text(subtitle)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }

        Spacer()
      }
      .padding(.vertical, OmiSpacing.xs)
      .padding(.horizontal, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.controlRadius, style: .continuous)
          .fill(isSelected ? Ink.accent.opacity(0.1) : Color.clear)
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
          .foregroundColor(unlocked ? Ink.accent : Ink.secondary)
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.hairline)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.stripRadius, style: .continuous)
              .fill(unlocked ? Ink.accent.opacity(0.15) : Ink.rowFill)
          )

        Text(name)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(unlocked ? Ink.primary : Ink.secondary)

        Spacer()

        if unlocked {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.listeningGreen)
        } else {
          Image(systemName: "lock.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      }

      HStack(spacing: OmiSpacing.sm) {
        Text(requirement)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)

        if let progress = progress, !unlocked {
          Text("(\(progress))")
            .scaledMonospacedDigitFont(size: 12)
            .foregroundColor(Ink.secondary)
        }
      }
    }
    .padding(.vertical, OmiSpacing.xxs)
  }

  func statRow(label: String, value: Int) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

      Spacer()

      Text(formatNumber(value))
        .scaledMonospacedDigitFont(size: 14, weight: .medium)
        .foregroundColor(Ink.primary)
    }
  }

  func statRowLoading(label: String) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

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
                  .foregroundColor(Ink.primary)

                if !updaterViewModel.activeChannelLabel.isEmpty {
                  Text("(\(updaterViewModel.activeChannelLabel))")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(Ink.secondary)
                }
              }

              Text("Version \(updaterViewModel.currentVersion) (\(updaterViewModel.buildNumber))")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
                .textSelection(.enabled)
            }

            Spacer()
          }

          Divider()
            .background(Ink.hairline)

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
                .foregroundColor(Ink.secondary)

              Spacer()

              Image(systemName: "arrow.right")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
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
              .foregroundColor(Ink.secondary)

            Text("Software Updates")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)

            Spacer()

            Button("Check Now") {
              updaterViewModel.checkForUpdates()
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            .disabled(!updaterViewModel.canManuallyCheckForUpdates)
            .help(
              updaterViewModel.canManuallyCheckForUpdates
                ? "Check for app updates"
                : updaterViewModel.updateSessionInProgress
                  ? "An update is already downloading…" : "Already checking for updates…")
          }

          if let lastCheck = updaterViewModel.lastUpdateCheckDate {
            Text("Last checked: \(lastCheck, style: .relative) ago")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }

          if let failure = updaterViewModel.lastUpdateFailure {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              HStack(alignment: .top, spacing: OmiSpacing.sm) {
                Image(systemName: "exclamationmark.triangle.fill")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(SettingsInk.notice)

                VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                  Text("Update Needs Attention")
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundColor(Ink.primary)
                  Text(failure.userMessage)
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                }
              }

              HStack(spacing: OmiSpacing.sm) {
                if failure.isRecoverableLaunchLocation {
                  Button("Open Applications") {
                    NSWorkspace.shared.open(
                      URL(fileURLWithPath: "/Applications", isDirectory: true))
                  }
                  .buttonStyle(OmiButtonStyle(.primary, size: .compact))
                }

                Button("Download Latest") {
                  openURLInDefaultBrowser(AppBuild.manualDownloadURL)
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))

                Button("Dismiss") {
                  updaterViewModel.lastUpdateFailure = nil
                }
                .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              }
            }
            .padding(OmiSpacing.md)
            .background(Ink.rowFill)
            .cornerRadius(SettingsGlassMetrics.controlRadius)
          }

          Divider()
            .background(Ink.hairline)

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
              .foregroundColor(Ink.secondary)
          } else if AppBuild.isNamedDevelopmentBundle {
            Text("Named developer bundles do not use shared Sparkle updates. Run omi-dev update instead.")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          } else if AnalyticsManager.isDevBuild {
            Text(
              "Development builds keep automatic installation disabled to avoid replacing the local app."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
          }

          Divider()
            .background(Ink.hairline)

          settingRow(
            title: "Update Channel", subtitle: updaterViewModel.updateChannel.description,
            settingId: "about.channel"
          ) {
            if AppBuild.isBetaProductionBundle {
              // Omi Beta is permanently a beta-channel client; switching it to stable
              // would make Sparkle replace it with the stable-identity app in place.
              Text(UpdateChannel.beta.displayName)
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            } else {
              SettingsMenuPicker(
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
            }
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
            .foregroundColor(Ink.secondary)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Report an Issue")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(Ink.primary)

            Text("Help us improve omi")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }

          Spacer()

          Button("Report") {
            FeedbackWindow.show(userEmail: AuthState.shared.userEmail)
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        }
      }
    }
  }

  // MARK: - Helper Views

  /// A printed chord in a settings row. The one place a monospaced face appears on this surface, and
  /// it is `SettingsKeyHint` rather than a second spelling of one.
  func fontShortcutRow(label: String, keys: String) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
      Spacer()
      SettingsKeyHint(text: keys)
    }
  }

  /// The card every settings block sits on.
  ///
  /// The corner is `SettingsGlassMetrics.cardRadius` and **not** `InkGlass.cornerRadius`: 22 is the
  /// corner of the glass itself, and a card drawn inside the panel at the panel's own radius reads as
  /// a second pane rather than as content on the first.
  func settingsCard<Content: View>(
    settingId: String? = nil, @ViewBuilder content: () -> Content
  ) -> some View {
    let card = content()
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(OmiSpacing.lg)
      .settingsGlassCard()
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

  /// A labelled control inside a card: a title, a sentence under it, and the control on the right.
  ///
  /// The title is `Ink.primary` and the subtitle `Ink.secondary` — the two rungs glass carries. They
  /// were `secondary`/`tertiary` under the dark palette, which is the same *pair* one step down; on
  /// glass the bottom rung is `Ink.secondary` (see its doc comment), so keeping the pair means moving
  /// both up rather than flattening the title into its own subtitle.
  func settingRow<Content: View>(
    title: String, subtitle: String, settingId: String? = nil, @ViewBuilder control: () -> Content
  ) -> some View {
    let row = HStack {
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
        Text(subtitle)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
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

  /// A card's own heading: the icon in the tile every settings row uses, and the title beside it.
  ///
  /// The tile rather than a bare glyph, for the reason `SettingsIconTile` exists — a column of SF
  /// Symbols at wildly different optical weights only lines up on a fixed ground.
  func settingsCardHeader(icon: String, title: String) -> some View {
    HStack(spacing: SettingsGlassMetrics.rowContentSpacing) {
      SettingsIconTile(symbol: icon)

      Text(title)
        .scaledFont(size: OmiType.subheading, weight: .medium)
        .foregroundColor(Ink.primary)
    }
  }

  func performStepHaptic() {
    NSHapticFeedbackManager.defaultPerformer.perform(.alignment, performanceTime: .now)
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
          .foregroundColor(Ink.secondary)

        Spacer()

        Image(systemName: "arrow.up.right")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }
    }
    .buttonStyle(.plain)
  }

  func trackingItem(_ text: String) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Circle()
        .fill(Ink.hairline)
        .frame(width: 4, height: 4)

      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
    }
  }

  func privacyBullet(_ text: String) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "checkmark")
        .scaledFont(size: OmiType.micro, weight: .bold)
        .foregroundColor(Ink.listeningGreen)

      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
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
          .foregroundColor(Ink.secondary)
          .frame(width: 20, alignment: .leading)

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(title)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)

          Text(subtitle)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
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
