import AppKit
import OmiTheme
import SwiftUI

extension SettingsContentView {
  /// Everything about the version you are running and the version you could be running.
  ///
  /// This lives apart from About because the two answer different questions. About is identity and
  /// legal links — what this app is. Updates is a thing you *do*: check, install, decide whether it
  /// happens on its own, and read what changed. Before this section the update controls were the
  /// second card on an About page nobody opens for them, and "What's New" was a link that left the
  /// app for a GitHub release page. The notes are bundled with the build, so they read offline.
  var updatesSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      updateStatusCard
      updatePreferencesCard
      releaseNotesCard
    }
  }

  // MARK: - Status

  private var updateStatus: DesktopUpdateStatusPresentation.Kind {
    DesktopUpdateStatusPresentation.kind(
      sessionInProgress: updaterViewModel.updateSessionInProgress,
      updateAvailable: updaterViewModel.updateAvailable,
      availableVersion: updaterViewModel.availableVersion,
      restartImminent: updaterViewModel.updateRestartImminent,
      deferredForRecording: updaterViewModel.updateDeferredForActiveRecording,
      userInitiatedCheck: updaterViewModel.userInitiatedCheckInProgress
    )
  }

  private var updateStatusCard: some View {
    settingsCard(settingId: "updates.status") {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        HStack(spacing: OmiSpacing.lg) {
          // The locator, not `Bundle.resourceBundle.url(forResource:)`, for the reason
          // `DesktopReleaseNotesCatalog.loadBundled` documents: flat `.process("Resources")` files
          // sit outside the bundle's `resourcePath`, so the lookup silently returns nil.
          if let logoURL = OmiSoundAssetLocator.bundled.url(forFileName: "herologo.png"),
            let logoImage = NSImage(contentsOf: logoURL)
          {
            Image(nsImage: logoImage)
              .resizable()
              .aspectRatio(contentMode: .fit)
              .frame(width: 40, height: 40)
          }

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack(spacing: OmiSpacing.xs) {
              Text("omi")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(Ink.primary)

              if !updaterViewModel.activeChannelLabel.isEmpty {
                Text(updaterViewModel.activeChannelLabel)
                  .scaledFont(size: OmiType.caption, weight: .medium)
                  .foregroundColor(Ink.secondary)
                  .padding(.horizontal, OmiSpacing.xs)
                  .padding(.vertical, OmiSpacing.hairline)
                  .background(Ink.rowFill)
                  .cornerRadius(OmiChrome.elementRadius)
              }
            }

            Text("Version \(updaterViewModel.currentVersion) (\(updaterViewModel.buildNumber))")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
              .textSelection(.enabled)
          }

          Spacer()

          Button(updateStatus.checkActionTitle) {
            updaterViewModel.checkForUpdates()
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          .disabled(!updaterViewModel.canManuallyCheckForUpdates)
          .accessibilityIdentifier("settings-updates-check-button")
          .help(
            updaterViewModel.canManuallyCheckForUpdates
              ? "Check for app updates"
              : updaterViewModel.updateSessionInProgress
                ? "An update is already in progress…" : "Already checking for updates…")
        }

        if updateStatus.isVisible {
          HStack(alignment: .center, spacing: OmiSpacing.sm) {
            if updateStatus.showsProgress {
              ProgressView()
                .controlSize(.small)
            } else {
              Image(systemName: "arrow.down.circle.fill")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.accent)
            }

            VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
              Text(updateStatus.title)
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(Ink.primary)
              if let detail = updateStatus.detail {
                Text(detail)
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)
              }
            }
            Spacer(minLength: 0)
          }
          .padding(OmiSpacing.md)
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(Ink.rowFill)
          .cornerRadius(OmiChrome.elementRadius)
          .accessibilityIdentifier("settings-update-status")
          .accessibilityLabel(updateStatus.accessibilityLabel)
        }

        if let lastCheck = updaterViewModel.lastUpdateCheckDate {
          Text("Last checked: \(lastCheck, style: .relative) ago")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }

        if let failure = updaterViewModel.lastUpdateFailure {
          updateFailureBlock(failure)
        }
      }
    }
  }

  private func updateFailureBlock(_ failure: UpdateFailureDiagnostics) -> some View {
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
            NSWorkspace.shared.open(URL(fileURLWithPath: "/Applications", isDirectory: true))
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

  // MARK: - Preferences

  private var updatePreferencesCard: some View {
    settingsCard(settingId: "updates.preferences") {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        settingsCardHeader(icon: "arrow.triangle.2.circlepath", title: "Automatic Updates")

        settingRow(
          title: "Check Automatically",
          subtitle: "Look for updates in the background",
          settingId: "updates.autocheck"
        ) {
          Toggle("", isOn: $updaterViewModel.automaticallyChecksForUpdates)
            .toggleStyle(OmiToggleStyle())
            .labelsHidden()
            .disabled(updaterViewModel.usesManagedUpdatePolicy || AnalyticsManager.isDevBuild)
        }

        if updaterViewModel.automaticallyChecksForUpdates {
          settingRow(
            title: "Install Automatically",
            subtitle: "Download and install updates when they are available",
            settingId: "updates.autoinstall"
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
          Text(
            "Named developer bundles do not use shared Sparkle updates. Run omi-dev update instead."
          )
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        } else if AnalyticsManager.isDevBuild {
          Text(
            "Development builds keep automatic installation disabled to avoid replacing the local app."
          )
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        }

        GlassSeparator()

        if !AppBuild.isBetaProductionBundle {
          settingRow(
            title: "Omi Beta",
            subtitle: "Install the separate Omi Beta app. It runs beside this one.",
            settingId: "updates.channel"
          ) {
            Button("Get Omi Beta") {
              openURLInDefaultBrowser(AppBuild.omiBetaInstallURL)
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          }
        } else {
          settingRow(
            title: "Omi Beta",
            subtitle: "This app updates from the Beta feed and runs beside Omi.",
            settingId: "updates.channel"
          ) {
            Text("Installed")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }
        }
      }
    }
  }

  // MARK: - Release notes

  private var releaseNotesCard: some View {
    settingsCard(settingId: "updates.releasenotes") {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        settingsCardHeader(icon: "sparkles", title: "What's New")

        let releases = DesktopReleaseNotesCatalog.bundled.releases
        if releases.isEmpty {
          Text("Release notes are not bundled with this build.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        } else {
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            ForEach(Array(releases.prefix(releaseNotesDisclosure.visibleCount))) { release in
              releaseNoteRow(release, isNewest: release.id == releases.first?.id)
            }
          }
          .accessibilityIdentifier("settings-release-notes")

          if releaseNotesDisclosure.canShowMore(total: releases.count) {
            Button("Show More Releases") {
              releaseNotesDisclosure.showMore(total: releases.count)
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            .accessibilityIdentifier("settings-release-notes-more")
          }
        }

        GlassSeparator()

        linkRow(title: "All Releases on GitHub", url: AppBuild.changelogURLString)
      }
    }
  }

  /// One release: its version and date, and the notes that shipped with it. The newest release is
  /// open on arrival — it is the reason the section exists — and the rest expand on click, so a
  /// version you are looking for stays one scroll away rather than buried in every note ever written.
  private func releaseNoteRow(_ release: DesktopReleaseNote, isNewest: Bool) -> some View {
    let isExpanded = releaseNotesDisclosure.isExpanded(release.version, isNewest: isNewest)
    let isInstalled = release.version == updaterViewModel.currentVersion

    return VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Button(action: {
        releaseNotesDisclosure.toggle(release.version, isNewest: isNewest)
      }) {
        HStack(spacing: OmiSpacing.sm) {
          Text(release.version)
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.primary)

          if isInstalled {
            Text("Installed")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(Ink.secondary)
              .padding(.horizontal, OmiSpacing.xs)
              .padding(.vertical, OmiSpacing.hairline)
              .background(Ink.rowFill)
              .cornerRadius(OmiChrome.elementRadius)
          }

          if let date = release.date {
            Text(date, style: .date)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }

          Spacer()

          if !isNewest {
            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(isNewest)
      .accessibilityIdentifier("settings-release-note-\(release.version)")

      if isExpanded {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          ForEach(Array(release.changes.enumerated()), id: \.offset) { _, change in
            HStack(alignment: .top, spacing: OmiSpacing.sm) {
              Circle()
                .fill(Ink.hairline)
                .frame(width: 4, height: 4)
                .padding(.top, OmiSpacing.xs)

              Text(change)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
      }
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .cornerRadius(SettingsGlassMetrics.controlRadius)
  }
}
