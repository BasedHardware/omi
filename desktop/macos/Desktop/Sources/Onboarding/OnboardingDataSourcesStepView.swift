import OmiTheme
import SwiftUI

struct OnboardingDataSourcesStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onSkip: (() -> Void)?
  let onForceComplete: (() -> Void)?

  @State private var activeImportSource: OnboardingMemoryLogSource?
  @State private var chatGPTMemoryLog = ""
  @State private var claudeMemoryLog = ""

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "",
      title: "Your 2nd brain is live.",
      description: "Connect more of your context.",
      rightPaneFooterText: coordinator.connectedContextSummary,
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        connectionsList

        if let error = coordinator.lastActionError {
          Text(error)
            .inkStyle(InkType.statusLabel, color: PageGlass.warning)
            .fixedSize(horizontal: false, vertical: true)
        }

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if coordinator.isResearchComplete {
            Button("Continue") {
              onContinue()
            }
            .buttonStyle(InkButtonStyle(kind: .primary))
            .keyboardShortcut(.defaultAction)
            // Opacity only: a capsule this size scaling in reads as a toy.
            .transition(.opacity)
          } else {
            HStack(spacing: OmiSpacing.sm) {
              ProgressView()
                .controlSize(.small)
                .tint(Ink.secondary)
              Text("Scanning your data sources...")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Ink.secondary)
            }
          }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await graphViewModel.addGraphFromStorage()
        if !coordinator.isResearchComplete {
          await coordinator.startBackgroundInsightsIfNeeded()
        }
      }
      .sheet(isPresented: $coordinator.showingGmailAccountPicker) {
        GmailAccountPickerView(
          accounts: coordinator.gmailAccounts,
          selectedCookiePath: GmailSelectionStore.selectedCookiePath,
          hasMadeChoice: GmailSelectionStore.hasMadeChoice,
          onSelect: { cookiePath, label in
            coordinator.selectGmailAccount(cookiePath, label: label)
          },
          onCancel: { coordinator.cancelGmailAccountSelection() }
        )
      }
    }
  }

  private var connectionsList: some View {
    VStack(alignment: .leading, spacing: 0) {
      compactSourceRow(
        brand: .calendar,
        title: "Calendar",
        metrics: metricsText(
          sourceCount: coordinator.calendarInsightCount,
          sourceSingular: "event",
          sourcePlural: "events",
          memoryCount: coordinator.calendarMemoriesSaved
        ),
        isOn: true,
        isDisabled: true,
        scanFinished: coordinator.calendarInsightsFinished,
        scanDeferred: coordinator.calendarInsightsDeferred,
        scanFailed: coordinator.calendarInsightsFailed
      )
      listDivider

      compactSourceRow(
        brand: .gmail,
        title: "Email",
        metrics: metricsText(
          sourceCount: coordinator.gmailInsightCount,
          sourceSingular: "email",
          sourcePlural: "emails",
          memoryCount: coordinator.gmailMemoriesSaved
        ),
        isOn: true,
        isDisabled: true,
        scanFinished: coordinator.gmailInsightsFinished,
        scanDeferred: coordinator.gmailInsightsDeferred,
        scanFailed: coordinator.gmailInsightsFailed,
        actionTitle: "Choose account",
        action: {
          Task {
            await coordinator.loadGmailAccounts()
            guard !coordinator.gmailAccounts.isEmpty else { return }
            coordinator.showingGmailAccountPicker = true
          }
        }
      )
      listDivider

      compactSourceRow(
        brand: .localFiles,
        title: "Local files",
        metrics: metricsText(
          sourceCount: coordinator.scanSnapshot?.fileCount ?? 0,
          sourceSingular: "file",
          sourcePlural: "files",
          memoryCount: coordinator.localFileMemoriesSaved
        ),
        isOn: true,
        isDisabled: true
      )
      listDivider

      compactSourceRow(
        brand: .appleNotes,
        title: "Apple Notes",
        metrics: metricsText(
          sourceCount: coordinator.appleNotesInsightCount,
          sourceSingular: "note",
          sourcePlural: "notes",
          memoryCount: coordinator.appleNotesMemoriesSaved
        ),
        isOn: true,
        isDisabled: coordinator.appleNotesInsightCount > 0,
        scanFinished: coordinator.appleNotesInsightsFinished,
        scanFailed: coordinator.appleNotesInsightsFailed,
        actionTitle: coordinator.appleNotesInsightCount > 0 ? nil : "Select Folder",
        action: coordinator.appleNotesInsightCount > 0
          ? nil
          : {
            Task {
              await coordinator.selectAppleNotesFolderAndSync()
            }
          }
      )
      listDivider

      compactMemoryLogRow(source: .chatgpt)
      if activeImportSource == .chatgpt {
        listDivider
        memoryLogPanel(source: .chatgpt, text: $chatGPTMemoryLog)
          .padding(.horizontal, OmiSpacing.lg)
          .padding(.vertical, OmiSpacing.lg)
      }
      listDivider

      compactMemoryLogRow(source: .claude)
      if activeImportSource == .claude {
        listDivider
        memoryLogPanel(source: .claude, text: $claudeMemoryLog)
          .padding(.horizontal, OmiSpacing.lg)
          .padding(.vertical, OmiSpacing.lg)
      }
    }
    .glassCard()
  }

  private var listDivider: some View {
    GlassSeparator()
      .padding(.leading, 66)
  }

  private func compactMemoryLogRow(source: OnboardingMemoryLogSource) -> some View {
    let importedCount = coordinator.importedMemoryCount(for: source)
    let isExpanded = activeImportSource == source
    let isConnected = importedCount > 0

    return compactSourceRow(
      brand: source == .chatgpt ? .chatgpt : .claude,
      title: source.displayName,
      metrics: isConnected
        ? countLabel(importedCount, singular: "memory", plural: "memories")
        : "0 memories",
      isOn: isConnected || isExpanded,
      isDisabled: isConnected,
      onToggle: { enabled in
        activeImportSource = enabled ? source : nil
      }
    )
  }

  private func memoryLogPanel(
    source: OnboardingMemoryLogSource,
    text: Binding<String>
  ) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Open \(source.displayName), paste the copied prompt, then drop the full response here.")
        .font(.system(size: 13))
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)

      Button("Open \(source.displayName) and Copy Prompt") {
        coordinator.copyPromptAndOpenMemoryLogSource(source)
      }
      .buttonStyle(InkButtonStyle(kind: .primary))

      ZStack(alignment: .topLeading) {
        if text.wrappedValue.isEmpty {
          Text("Paste the full \(source.displayName) response here…")
            .font(.system(size: 13))
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.md)
        }

        TextEditor(text: text)
          .scrollContentBackground(.hidden)
          .font(.system(size: 13))
          .foregroundColor(Ink.primary)
          .frame(minHeight: 160)
          .padding(OmiSpacing.sm)
      }
      .frame(maxWidth: 560)
      .glassField()

      HStack(spacing: OmiSpacing.md) {
        Button(
          coordinator.isImportingMemoryLog(for: source)
            ? "Importing…" : "Import \(source.displayName)"
        ) {
          Task {
            await coordinator.importMemoryLog(text.wrappedValue, source: source)
            if coordinator.importedMemoryCount(for: source) > 0 {
              text.wrappedValue = ""
              activeImportSource = nil
            }
          }
        }
        .buttonStyle(InkButtonStyle(kind: .primary))
        .disabled(
          coordinator.isImportingMemoryLog(for: source)
            || text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

        Button("Cancel") {
          activeImportSource = nil
        }
        .buttonStyle(.plain)
        .foregroundColor(Ink.secondary)
        .font(.system(size: 13, weight: .medium))
      }
    }
    .padding(OmiSpacing.lg)
    .glassCard()
  }

  private func compactSourceRow(
    brand: ConnectorBrand,
    title: String,
    metrics: String,
    isOn: Bool,
    isDisabled: Bool,
    scanFinished: Bool? = nil,
    scanDeferred: Bool = false,
    scanFailed: Bool = false,
    actionTitle: String? = nil,
    action: (() -> Void)? = nil,
    onToggle: ((Bool) -> Void)? = nil
  ) -> some View {
    let status = OnboardingDataSourceRowStatus.resolve(
      metrics: metrics,
      scanFinished: scanFinished,
      scanDeferred: scanDeferred,
      scanFailed: scanFailed
    )

    return HStack(alignment: .center, spacing: OmiSpacing.md) {
      ConnectorBrandIcon(brand: brand, size: 38, cornerRadius: OmiChrome.smallControlRadius)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          .fixedSize(horizontal: false, vertical: true)

        Text(status.text)
          .inkStyle(InkType.statusLabel, color: status.isError ? PageGlass.warning : Ink.secondary)
          .monospacedDigit()
          .lineLimit(1)
      }
      .frame(minWidth: 130, alignment: .leading)

      Spacer(minLength: 8)

      if let actionTitle, let action {
        Button(actionTitle, action: action)
          .buttonStyle(.plain)
          .font(.system(size: 11, weight: .semibold))
          .foregroundColor(Ink.secondary)
          .fixedSize()
      }

      Toggle(
        "",
        isOn: Binding(
          get: { isOn },
          set: { onToggle?($0) }
        )
      )
      .labelsHidden()
      .toggleStyle(OmiToggleStyle())
      .disabled(isDisabled || onToggle == nil)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
  }

  private func metricsText(
    sourceCount: Int,
    sourceSingular: String,
    sourcePlural: String,
    memoryCount: Int
  ) -> String {
    let sourceText = countLabel(sourceCount, singular: sourceSingular, plural: sourcePlural)
    let memoryText = countLabel(memoryCount, singular: "memory", plural: "memories")
    return "\(sourceText) • \(memoryText)"
  }

  private func countLabel(_ count: Int, singular: String, plural: String) -> String {
    count == 1 ? "1 \(singular)" : "\(count.formatted()) \(plural)"
  }
}

struct OnboardingDataSourceRowStatus: Equatable {
  let text: String
  let isError: Bool

  static func resolve(
    metrics: String,
    scanFinished: Bool?,
    scanDeferred: Bool = false,
    scanFailed: Bool
  ) -> OnboardingDataSourceRowStatus {
    if scanDeferred {
      return OnboardingDataSourceRowStatus(
        text: "Connect in Apps to import",
        isError: false
      )
    }

    if scanFailed {
      return OnboardingDataSourceRowStatus(
        text: "Couldn't read - check access",
        isError: true
      )
    }

    if scanFinished == false {
      return OnboardingDataSourceRowStatus(text: "Scanning...", isError: false)
    }

    return OnboardingDataSourceRowStatus(text: metrics, isError: false)
  }
}
