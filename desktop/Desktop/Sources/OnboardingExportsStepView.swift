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

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "",
      title: "Put your memories where you work.",
      description: "Connect the tools where you want Omi context to live.",
      rightPaneFooterText: summaryText,
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: 18) {
        destinationsList

        if let activeDestination {
          exportPanel(for: activeDestination)
        }

        Button("Continue") {
          onContinue()
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await graphViewModel.addGraphFromStorage()
        statuses = await MemoryExportService.shared.allStatuses()
      }
    }
  }

  private var destinationsList: some View {
    VStack(alignment: .leading, spacing: 0) {
      ForEach(Array(MemoryExportDestination.allCases.enumerated()), id: \.element.id) {
        index, destination in
        exportRow(destination: destination)
        if index < MemoryExportDestination.allCases.count - 1 {
          Divider()
            .padding(.leading, 66)
            .background(Color.white.opacity(0.05))
        }
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

  private func exportRow(destination: MemoryExportDestination) -> some View {
    let status =
      statuses[destination]
      ?? MemoryExportStatus(
        exportedCount: 0, lastExportedAt: nil, detailText: nil, isConfigured: false)
    let metrics = exportMetrics(for: destination, status: status)

    return HStack(alignment: .center, spacing: 12) {
      ConnectorBrandIcon(brand: destination.brand, size: 38, cornerRadius: 11)

      VStack(alignment: .leading, spacing: 3) {
        Text(destination.title)
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
        Text(metrics)
          .font(.system(size: 12))
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer(minLength: 12)

      Button(activeDestination == destination ? "Close" : "Connect") {
        activeDestination = activeDestination == destination ? nil : destination
      }
      .buttonStyle(.plain)
      .font(.system(size: 13, weight: .semibold))
      .foregroundColor(OmiColors.textSecondary)
      .padding(.horizontal, 12)
      .padding(.vertical, 8)
      .background(
        Capsule(style: .continuous)
          .fill(OmiColors.backgroundPrimary)
      )
      .overlay(
        Capsule(style: .continuous)
          .stroke(Color.white.opacity(0.08), lineWidth: 1)
      )
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 14)
  }

  private func exportPanel(for destination: MemoryExportDestination) -> some View {
    OnboardingInlineExportPanel(
      destination: destination,
      statuses: $statuses,
      onClose: { activeDestination = nil }
    )
  }

  private func exportMetrics(
    for destination: MemoryExportDestination,
    status: MemoryExportStatus
  ) -> String {
    if status.exportedCount > 0 {
      return "\(status.exportedCount.formatted()) memories exported"
    }
    if destination.isAutomated {
      return "Automatic export"
    }
    if destination == .notion {
      return "Copy-ready page"
    }
    return "Prompt + memory pack"
  }
}

private struct OnboardingInlineExportPanel: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]
  let onClose: () -> Void

  @StateObject private var model = MemoryExportDestinationSheetModel()

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text(destination.description)
        .font(.system(size: 13))
        .foregroundColor(OmiColors.textSecondary)

      switch destination {
      case .notion:
        inlineInfoCard(
          "Omi copies a ready-to-paste memory page, saves a backup in Downloads, and opens Notion."
        )

      case .obsidian:
        inlineInfoCard(
          model.obsidianVaultPath.isEmpty
            ? "Pick your Obsidian vault once. Omi will keep refreshing `Omi/Memories.md` there."
            : model.obsidianVaultPath
        )

        Button(model.obsidianVaultPath.isEmpty ? "Choose vault" : "Change vault") {
          model.pickObsidianVault()
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)
        .font(.system(size: 12, weight: .medium))

      case .chatgpt, .claude, .gemini:
        inlineInfoCard(
          "Omi copies the prompt and memory pack together, saves a Markdown backup, and opens \(destination.title)."
        )
      }

      HStack(spacing: 12) {
        Button(model.isRunning ? runningLabel : idleLabel) {
          Task {
            if let updatedStatus = await model.run(destination: destination) {
              statuses[destination] = updatedStatus
            }
          }
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        .disabled(model.isRunning)

        Button("Cancel") {
          onClose()
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)
        .font(.system(size: 13, weight: .medium))
      }

      if let statusMessage = model.statusMessage {
        Text(statusMessage)
          .font(.system(size: 12, weight: .medium))
          .foregroundColor(OmiColors.success)
      }

      if let errorMessage = model.errorMessage {
        Text(errorMessage)
          .font(.system(size: 12, weight: .medium))
          .foregroundColor(OmiColors.warning)
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
    .task {
      await model.loadConfiguration()
    }
  }

  private var runningLabel: String {
    switch destination {
    case .notion: return "Preparing…"
    case .obsidian: return "Exporting…"
    case .chatgpt, .claude, .gemini: return "Preparing…"
    }
  }

  private var idleLabel: String {
    switch destination {
    case .notion:
      return "Copy & open"
    case .obsidian:
      return model.obsidianVaultPath.isEmpty ? "Choose vault" : "Export"
    case .chatgpt, .claude, .gemini:
      return "Copy & open"
    }
  }

  private func inlineTextField(
    _ placeholder: String,
    text: Binding<String>,
    secure: Bool = false
  ) -> some View {
    Group {
      if secure {
        SecureField(placeholder, text: text)
      } else {
        TextField(placeholder, text: text)
      }
    }
    .textFieldStyle(.plain)
    .font(.system(size: 13))
    .foregroundColor(OmiColors.textPrimary)
    .padding(.horizontal, 14)
    .padding(.vertical, 12)
    .background(
      RoundedRectangle(cornerRadius: 16, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: 16, style: .continuous)
            .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    )
  }

  private func inlineInfoCard(_ text: String) -> some View {
    Text(text)
      .font(.system(size: 12))
      .foregroundColor(OmiColors.textTertiary)
      .padding(14)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 16, style: .continuous)
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
              .stroke(Color.white.opacity(0.08), lineWidth: 1)
          )
      )
  }
}
