import OmiTheme
import SwiftUI

struct OnboardingExportsStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let summaryText: String
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var statuses: [MemoryExportDestination: MemoryExportStatus] = [:]
  @State private var activeDestination: MemoryExportDestination?
  @State private var showMore = false

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "",
      title: "Use Omi memory where you work.",
      description: "Export Omi context to the tools you already use.",
      rightPaneFooterText: summaryText,
      graphLeading: true,
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        destinationsList

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          Button("Continue") {
            onContinue()
          }
          .buttonStyle(OmiButtonStyle(.primary))
          .keyboardShortcut(.defaultAction)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await graphViewModel.addGraphFromStorage()
        statuses = await MemoryExportService.shared.allStatuses()
      }
    }
    .dismissableSheet(item: $activeDestination) { destination in
      // Same end-to-end MCP connect flow as the main-app connect screen:
      // grouped picker for Claude / Claude Code and ChatGPT / Codex, full
      // destination sheet for everything else.
      ConnectDestinationSheet(
        destination: destination,
        statuses: $statuses,
        onDismiss: { activeDestination = nil }
      )
      .frame(width: 520, height: 620)
    }
  }

  /// Mirrors the main-app "Use omi memory anywhere" stack: combined rows for
  /// Claude / Claude Code and ChatGPT / Codex, then the other MCP destinations.
  private var primaryEntries: [OnboardingExportEntry] {
    [
      OnboardingExportEntry(destination: .notion),
      OnboardingExportEntry(destination: .obsidian),
      OnboardingExportEntry(
        destination: .claudeCode, titleOverride: "Claude / Claude Code", brandOverride: .claude,
        connectionGroup: [.claude, .claudeCode]),
      OnboardingExportEntry(
        destination: .chatgpt, titleOverride: "ChatGPT / Codex",
        connectionGroup: [.chatgpt, .codex]),
      OnboardingExportEntry(destination: .openclaw),
      OnboardingExportEntry(destination: .hermes),
    ]
  }

  private var moreEntries: [OnboardingExportEntry] {
    [
      OnboardingExportEntry(destination: .claude),
      OnboardingExportEntry(destination: .codex),
      OnboardingExportEntry(destination: .gemini),
      OnboardingExportEntry(destination: .agents),
    ]
  }

  private var visibleEntries: [OnboardingExportEntry] {
    showMore ? primaryEntries + moreEntries : primaryEntries
  }

  private var destinationsList: some View {
    VStack(alignment: .leading, spacing: 0) {
      ForEach(visibleEntries) { entry in
        exportRow(entry: entry)
        Divider()
          .padding(.leading, 66)
          .background(Color.white.opacity(0.05))
      }
      moreRow
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

  private var moreRow: some View {
    Button {
      showMore.toggle()
    } label: {
      HStack(alignment: .center, spacing: OmiSpacing.md) {
        Image(systemName: showMore ? "minus" : "plus")
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 38, height: 38)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
              .fill(OmiColors.backgroundPrimary)
          )

        Text(showMore ? "Less" : "More")
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)

        Spacer(minLength: 12)
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
  }

  private func exportRow(entry: OnboardingExportEntry) -> some View {
    let destination = entry.destination
    let status =
      statuses[destination]
      ?? MemoryExportStatus(
        exportedCount: 0, lastExportedAt: nil, detailText: nil, isConfigured: false, hasConnection: false)
    let groupConnected = entry.connectionGroup.contains { statuses[$0]?.hasConnection == true }
    let metrics = exportMetrics(for: destination, status: status, groupConnected: groupConnected)

    return HStack(alignment: .center, spacing: OmiSpacing.md) {
      ConnectorBrandIcon(brand: entry.brand, size: 38, cornerRadius: OmiChrome.smallControlRadius)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(entry.title)
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
        Text(metrics)
          .font(.system(size: 12))
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer(minLength: 12)

      Button("Connect") {
        activeDestination = destination
      }
      .buttonStyle(.plain)
      .font(.system(size: 13, weight: .semibold))
      .foregroundColor(OmiColors.textSecondary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        Capsule(style: .continuous)
          .fill(OmiColors.backgroundPrimary)
      )
      .overlay(
        Capsule(style: .continuous)
          .stroke(Color.white.opacity(0.08), lineWidth: 1)
      )
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
  }

  private func exportMetrics(
    for destination: MemoryExportDestination,
    status: MemoryExportStatus,
    groupConnected: Bool = false
  ) -> String {
    if destination.supportsMCP {
      return status.hasConnection || groupConnected ? "Connected — live memory" : "Live connection"
    }
    if status.exportedCount > 0 {
      return "\(status.exportedCount.formatted()) memories exported"
    }
    if destination.isAutomated {
      return "Automatic export"
    }
    if destination == .notion {
      return "Copy-ready page"
    }
    if destination.supportsAgentSetup {
      return status.isConfigured ? "Agent prompt ready" : "Connect an agent"
    }
    return "Prompt + memory pack"
  }
}

private struct OnboardingExportEntry: Identifiable {
  let destination: MemoryExportDestination
  var titleOverride: String? = nil
  var brandOverride: ConnectorBrand? = nil
  var connectionGroup: [MemoryExportDestination] = []

  var id: String { destination.rawValue }
  var title: String { titleOverride ?? destination.title }
  var brand: ConnectorBrand { brandOverride ?? destination.brand }
}
