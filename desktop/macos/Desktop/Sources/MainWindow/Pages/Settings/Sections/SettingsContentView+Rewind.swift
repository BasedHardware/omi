import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

/// What the Rewind storage card should say.
///
/// `RewindIndexer.getStats()` returns `nil` both before it has run and when the
/// Rewind database fails to open, so the card could not tell "not read yet"
/// from "could not be read" — a Rewind store that never opens left it reading
/// "Loading..." with no end and no way to retry. Resolving the caption from the
/// stats *and* whether a read has completed is what separates the two.
enum RewindStorageSummaryState: Equatable {
  case loading
  case loaded(caption: String)
  case unavailable

  static func resolve(
    stats: (total: Int, indexed: Int, storageSize: Int64)?,
    didCompleteRead: Bool
  ) -> RewindStorageSummaryState {
    if let stats {
      return .loaded(caption: "\(stats.total) frames • \(RewindStorage.formatBytes(stats.storageSize))")
    }
    return didCompleteRead ? .unavailable : .loading
  }
}

/// The storage card's contents. It owns whether a read has completed — the
/// parent's `rewindStats` alone cannot express that — and writes the result
/// back through the binding so there is still one stats value on the pane.
struct RewindStorageSummary: View {
  @Binding var stats: (total: Int, indexed: Int, storageSize: Int64)?
  @State private var didCompleteRead = false
  @State private var isReloading = false

  var body: some View {
    HStack {
      Image(systemName: "internaldrive.fill")
        .scaledFont(size: OmiType.subheading)
        .foregroundColor(Ink.secondary)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Storage")
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(Ink.primary)

        switch RewindStorageSummaryState.resolve(stats: stats, didCompleteRead: didCompleteRead) {
        case .loaded(let caption):
          Text(caption)
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        case .loading:
          Text("Loading…")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        case .unavailable:
          Text("Couldn't read Rewind storage")
            .scaledFont(size: OmiType.body)
            .foregroundColor(SettingsInk.notice)
        }
      }

      Spacer()

      if case .unavailable = RewindStorageSummaryState.resolve(
        stats: stats, didCompleteRead: didCompleteRead)
      {
        Button("Retry") {
          Task { await read() }
        }
        .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        .disabled(isReloading)
      }
    }
    .task { await read() }
  }

  private func read() async {
    guard !isReloading else { return }
    isReloading = true
    let next = await RewindIndexer.shared.getStats()
    stats = next
    didCompleteRead = true
    isReloading = false
  }
}

extension SettingsContentView {
  var rewindSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "rewind.knowledgegraph") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "point.3.connected.trianglepath.dotted")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Screen Knowledge Graph")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text("Build graph entries from screen OCR after you explicitly enable this setting")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            }

            Spacer()

            Toggle("", isOn: $rewindSettings.screenKnowledgeGraphExtractionEnabled)
              .toggleStyle(OmiToggleStyle())
              .onChange(of: rewindSettings.screenKnowledgeGraphExtractionEnabled) { _, enabled in
                if !enabled {
                  // Turning extraction off also revokes the separate consent to
                  // read screen history, so re-enabling never silently resumes a
                  // historical sweep the user opted into once.
                  rewindSettings.screenKnowledgeGraphHistoricalBackfillEnabled = false
                  Task { await ScreenKnowledgeGraphExtractor.shared.reset() }
                }
              }
          }

          Text(
            "OCR text stays on this Mac when on-device extraction is available. Screenshots are never uploaded. If you allow cloud fallback, OCR text may be sent to Omi's Gemini proxy."
          )
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)

          Text(
            "Graph entries are stored on this Mac and are kept independently of your screen history: deleting a screenshot, or letting it age out of your retention window, does not remove what was already extracted from it. Turning this off stops all further extraction but keeps existing entries — remove them from the knowledge graph to delete them."
          )
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)

          HStack {
            Text("Allow cloud fallback")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.secondary)

            Spacer()

            Toggle("", isOn: $rewindSettings.screenKnowledgeGraphCloudFallbackEnabled)
              .toggleStyle(OmiToggleStyle())
              .disabled(!rewindSettings.screenKnowledgeGraphExtractionEnabled)
              .onChange(of: rewindSettings.screenKnowledgeGraphCloudFallbackEnabled) { _, enabled in
                if enabled && rewindSettings.screenKnowledgeGraphExtractionEnabled {
                  Task { await ScreenKnowledgeGraphExtractor.shared.scheduleBackfillIfNeeded() }
                } else if !enabled {
                  Task { await ScreenKnowledgeGraphExtractor.shared.reset() }
                }
              }
          }

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack {
              Text("Include screen history from before you turned this on")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(Ink.secondary)

              Spacer()

              Toggle("", isOn: $rewindSettings.screenKnowledgeGraphHistoricalBackfillEnabled)
                .toggleStyle(OmiToggleStyle())
                .disabled(!rewindSettings.screenKnowledgeGraphExtractionEnabled)
                .onChange(of: rewindSettings.screenKnowledgeGraphHistoricalBackfillEnabled) { _, enabled in
                  if enabled && rewindSettings.screenKnowledgeGraphExtractionEnabled {
                    Task { await ScreenKnowledgeGraphExtractor.shared.scheduleBackfillIfNeeded() }
                  }
                }
            }

            Text(
              "Off by default. Extraction otherwise only reads screen captures taken after you turned it on; this reaches back through screen history you recorded before then."
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
          }
        }
      }

      // Storage Stats
      settingsCard(settingId: "rewind.storage") {
        RewindStorageSummary(stats: $rewindStats)
      }

      // Excluded Apps
      settingsCard(settingId: "rewind.excludedapps") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "eye.slash.fill")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Excluded Apps")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text("Screen capture is paused when these apps are active")
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.secondary)
            }

            Spacer()

            Button("Reset to Defaults") {
              rewindSettings.resetToDefaults()
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
          }

          GlassSeparator()

          // List of excluded apps
          if rewindSettings.excludedApps.isEmpty {
            HStack {
              Spacer()
              VStack(spacing: OmiSpacing.sm) {
                Image(systemName: "checkmark.shield")
                  .scaledFont(size: 24)
                  .foregroundColor(Ink.secondary)
                Text("No apps excluded")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
              }
              .padding(.vertical, OmiSpacing.lg)
              Spacer()
            }
          } else {
            // A rule between rows rather than a gap between them. A column of thirty app names on
            // one card ran together at `OmiSpacing.sm`: nothing said where one row ended, so it
            // read as a block of text with icons in it. The inset hairline is what makes it a list.
            let excluded = Array(rewindSettings.excludedApps).sorted()
            LazyVStack(spacing: 0) {
              ForEach(excluded, id: \.self) { appName in
                if appName != excluded.first { SettingsRowDivider() }
                ExcludedAppRow(
                  appName: appName,
                  onRemove: {
                    rewindSettings.includeApp(appName)
                  }
                )
                .padding(.vertical, SettingsGlassMetrics.rowVerticalPadding)
              }
            }
          }

          GlassSeparator()

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
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "battery.75percent")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Battery Optimization")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text(
                "On battery, Omi captures your screen less often to save power while keeping text recognition accurate."
              )
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
            }

            Spacer()

            Text("Automatic")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.secondary)
          }
        }
      }

      // Retention Settings
      settingsCard(settingId: "rewind.retention") {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack {
            Image(systemName: "clock.fill")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(Ink.secondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Data Retention")
                .scaledFont(size: OmiType.subheading, weight: .medium)
                .foregroundColor(Ink.primary)

              Text(
                rewindSettings.keepsEverything
                  ? "Rewind reaches back as far as you have been capturing"
                  : "Older screen recordings are deleted, and Rewind cannot reach past them"
              )
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
            }

            Spacer()

            SettingsMenuPicker(selection: $rewindSettings.retentionDays) {
              Text("3 days").tag(3)
              Text("7 days").tag(7)
              Text("14 days").tag(14)
              Text("30 days").tag(30)
              Text("Keep everything").tag(RewindSettings.unlimitedRetentionDays)
            }
          }
        }
      }
    }
  }

  // MARK: - Transcription Section

}
