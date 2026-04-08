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
      VStack(alignment: .leading, spacing: 18) {
        connectionsList

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.warning)
        }

        if coordinator.isResearchComplete {
          Button("Continue") {
            onContinue()
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
          .transition(.opacity.combined(with: .scale(scale: 0.95)))
        } else {
          HStack(spacing: 8) {
            ProgressView()
              .controlSize(.small)
              .tint(OmiColors.textTertiary)
            Text("Scanning your data sources...")
              .font(.system(size: 13, weight: .medium))
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await graphViewModel.addGraphFromStorage()
        if !coordinator.isResearchComplete {
          await coordinator.startBackgroundInsightsIfNeeded()
        }
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
        isDisabled: true
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
        isDisabled: true
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
          .padding(.horizontal, 16)
          .padding(.vertical, 16)
      }
      listDivider

      compactMemoryLogRow(source: .claude)
      if activeImportSource == .claude {
        listDivider
        memoryLogPanel(source: .claude, text: $claudeMemoryLog)
          .padding(.horizontal, 16)
          .padding(.vertical, 16)
      }
    }
    .background(
      RoundedRectangle(cornerRadius: 22, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: 22, style: .continuous)
            .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    )
  }

  private var listDivider: some View {
    Divider()
      .padding(.leading, 66)
      .background(Color.white.opacity(0.05))
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
    VStack(alignment: .leading, spacing: 14) {
      Text("Open \(source.displayName), paste the copied prompt, then drop the full response here.")
        .font(.system(size: 13))
        .foregroundColor(OmiColors.textSecondary)

      Button("Open \(source.displayName) and Copy Prompt") {
        coordinator.copyPromptAndOpenMemoryLogSource(source)
      }
      .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))

      ZStack(alignment: .topLeading) {
        RoundedRectangle(cornerRadius: 18, style: .continuous)
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
              .stroke(Color.white.opacity(0.08), lineWidth: 1)
          )

        if text.wrappedValue.isEmpty {
          Text("Paste the full \(source.displayName) response here…")
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, 14)
            .padding(.vertical, 14)
        }

        TextEditor(text: text)
          .scrollContentBackground(.hidden)
          .font(.system(size: 13))
          .foregroundColor(OmiColors.textPrimary)
          .frame(minHeight: 160)
          .padding(8)
      }
      .frame(maxWidth: 560)

      HStack(spacing: 12) {
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
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        .disabled(
          coordinator.isImportingMemoryLog(for: source)
            || text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

        Button("Cancel") {
          activeImportSource = nil
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)
        .font(.system(size: 13, weight: .medium))
      }
    }
    .padding(18)
    .background(
      RoundedRectangle(cornerRadius: 20, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: 20, style: .continuous)
            .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    )
  }

  private func compactSourceRow(
    brand: ConnectorBrand,
    title: String,
    metrics: String,
    isOn: Bool,
    isDisabled: Bool,
    actionTitle: String? = nil,
    action: (() -> Void)? = nil,
    onToggle: ((Bool) -> Void)? = nil
  ) -> some View {
    HStack(alignment: .center, spacing: 12) {
      ConnectorBrandIcon(brand: brand, size: 38, cornerRadius: 11)

      VStack(alignment: .leading, spacing: 3) {
        Text(title)
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)

        Text(metrics)
          .font(.system(size: 12, weight: .medium))
          .foregroundColor(OmiColors.textTertiary)
          .monospacedDigit()
          .lineLimit(1)
      }
      .frame(minWidth: 130, alignment: .leading)

      Spacer(minLength: 8)

      if let actionTitle, let action {
        Button(actionTitle, action: action)
          .buttonStyle(.plain)
          .font(.system(size: 11, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
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
      .toggleStyle(.switch)
      .disabled(isDisabled || onToggle == nil)
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 13)
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
