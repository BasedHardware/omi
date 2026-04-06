import AppKit
import SwiftUI

struct ExportsSection: View {
  private let destinations = MemoryExportDestination.allCases
  let statuses: [MemoryExportDestination: MemoryExportStatus]
  let onSelectDestination: (MemoryExportDestination) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("Exports")
        .scaledFont(size: 18, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      LazyVGrid(columns: [
        GridItem(.adaptive(minimum: 220), spacing: 16)
      ], spacing: 16) {
        ForEach(destinations) { destination in
          MemoryExportCard(
            destination: destination,
            status: statuses[destination] ?? MemoryExportStatus(
              exportedCount: 0, lastExportedAt: nil, detailText: nil, isConfigured: false)
          ) {
            onSelectDestination(destination)
          }
        }
      }
    }
  }
}

private struct MemoryExportCard: View {
  let destination: MemoryExportDestination
  let status: MemoryExportStatus
  let action: () -> Void

  @State private var isHovering = false

  private var primaryText: String {
    if status.exportedCount > 0 {
      return "\(status.exportedCount.formatted()) memories exported"
    }
    if let detail = status.detailText, !detail.isEmpty {
      return detail
    }
    return "Not connected"
  }

  private var secondaryText: String? {
    if let lastExportedAt = status.lastExportedAt {
      return "Updated \(RelativeDateTimeFormatter().localizedString(for: lastExportedAt, relativeTo: Date()))"
    }
    if let detail = status.detailText, !detail.isEmpty, detail != primaryText {
      return detail
    }
    return destination.isAutomated ? destination.subtitle : "Manual flow"
  }

  private var actionTitle: String {
    if destination.isAutomated {
      return status.isConfigured ? "Sync now" : "Connect"
    }
    return "Connect"
  }

  var body: some View {
    Button(action: action) {
      VStack(alignment: .leading, spacing: 10) {
        HStack(spacing: 12) {
          ConnectorBrandIcon(brand: destination.brand, size: 50, cornerRadius: 12)

          VStack(alignment: .leading, spacing: 4) {
            Text(destination.title)
              .scaledFont(size: 14, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
              .lineLimit(1)

            Text(destination.subtitle)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
          }

          Spacer()
        }

        Text(destination.description)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(2)
          .multilineTextAlignment(.leading)

        HStack {
          VStack(alignment: .leading, spacing: 3) {
            Text(primaryText)
              .scaledFont(size: 11, weight: .medium)
              .foregroundColor(status.exportedCount > 0 ? OmiColors.textSecondary : OmiColors.textTertiary)

            if let secondaryText {
              Text(secondaryText)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .lineLimit(1)
            }
          }

          Spacer()

          ImportConnectorActionButton(title: actionTitle, isConnected: status.isConfigured || status.exportedCount > 0)
        }
      }
      .padding(14)
      .background(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
      .cornerRadius(12)
      .overlay(
        RoundedRectangle(cornerRadius: 12)
          .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}

@MainActor
final class MemoryExportDestinationSheetModel: ObservableObject {
  @Published var isRunning = false
  @Published var statusMessage: String?
  @Published var errorMessage: String?
  @Published var notionToken = ""
  @Published var notionParentPageID = ""
  @Published var obsidianVaultPath = ""

  func loadConfiguration() async {
    let notion = await MemoryExportService.shared.notionConfiguration()
    notionToken = notion.token
    notionParentPageID = notion.parentPageID
    obsidianVaultPath = await MemoryExportService.shared.obsidianVaultPath()
  }

  func run(destination: MemoryExportDestination) async -> MemoryExportStatus? {
    errorMessage = nil
    statusMessage = nil
    isRunning = true
    defer { isRunning = false }

    do {
      switch destination {
      case .notion:
        let result = try await MemoryExportService.shared.exportToNotion(
          token: notionToken,
          parentPageID: notionParentPageID
        )
        await MainActor.run {
          if let url = result.destinationURL {
            NSWorkspace.shared.open(url)
          }
        }
        statusMessage = "Exported \(result.memoryCount.formatted()) memories to Notion."

      case .obsidian:
        let vaultURL: URL
        if obsidianVaultPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
          guard let pickedURL = selectObsidianVault() else {
            return nil
          }
          obsidianVaultPath = pickedURL.path
          vaultURL = pickedURL
        } else {
          vaultURL = URL(fileURLWithPath: obsidianVaultPath)
        }

        let result = try await MemoryExportService.shared.exportToObsidian(vaultURL: vaultURL)
        await MainActor.run {
          if let openURL = result.destinationURL {
            NSWorkspace.shared.open(openURL)
          } else if let fileURL = result.fileURL {
            NSWorkspace.shared.activateFileViewerSelecting([fileURL])
          }
        }
        statusMessage = "Wrote \(result.memoryCount.formatted()) memories into Obsidian."

      case .chatgpt, .claude, .gemini:
        let result = try await MemoryExportService.shared.prepareManualExport(for: destination)
        await MainActor.run {
          NSPasteboard.general.clearContents()
          NSPasteboard.general.setString(destination.manualPrompt, forType: .string)
          if let fileURL = result.fileURL {
            NSWorkspace.shared.activateFileViewerSelecting([fileURL])
          }
          if let openURL = result.destinationURL {
            NSWorkspace.shared.open(openURL)
          }
        }
        statusMessage = "Memory pack ready for \(destination.title). Prompt copied."
      }

      return await MemoryExportService.shared.status(for: destination)
    } catch {
      errorMessage = error.localizedDescription
      return nil
    }
  }

  func pickObsidianVault() {
    if let selectedURL = selectObsidianVault() {
      obsidianVaultPath = selectedURL.path
    }
  }

  private func selectObsidianVault() -> URL? {
    let panel = NSOpenPanel()
    panel.message = "Select your Obsidian vault."
    panel.prompt = "Open"
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    return panel.runModal() == .OK ? panel.url : nil
  }
}

struct MemoryExportDestinationSheet: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]
  let onDismiss: () -> Void

  @StateObject private var model = MemoryExportDestinationSheetModel()

  var body: some View {
    VStack(alignment: .leading, spacing: 18) {
      HStack(alignment: .top, spacing: 14) {
        ConnectorBrandIcon(brand: destination.brand, size: 56, cornerRadius: 16)

        VStack(alignment: .leading, spacing: 4) {
          Text(destination.title)
            .scaledFont(size: 20, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          Text(destination.subtitle)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textTertiary)

          Text(destination.description)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textSecondary)
            .padding(.top, 4)
        }

        Spacer()

        DismissButton(action: onDismiss)
      }

      content

      if let statusMessage = model.statusMessage {
        Text(statusMessage)
          .scaledFont(size: 12, weight: .medium)
          .foregroundColor(OmiColors.success)
      }

      if let errorMessage = model.errorMessage {
        Text(errorMessage)
          .scaledFont(size: 12, weight: .medium)
          .foregroundColor(OmiColors.warning)
      }

      Spacer(minLength: 0)
    }
    .padding(24)
    .background(OmiColors.backgroundPrimary)
    .task {
      await model.loadConfiguration()
    }
  }

  @ViewBuilder
  private var content: some View {
    switch destination {
    case .notion:
      VStack(alignment: .leading, spacing: 12) {
        textField("Notion integration token", text: $model.notionToken, isSecure: true)
        textField("Parent page ID", text: $model.notionParentPageID)
        Text("Omi creates a child page under this parent and writes your latest memories into it.")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }

    case .obsidian:
      VStack(alignment: .leading, spacing: 12) {
        textField("Vault path", text: $model.obsidianVaultPath)

        Button("Choose vault") {
          model.pickObsidianVault()
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)
        .scaledFont(size: 12, weight: .medium)

        Text("Omi writes a refreshed `Omi/Memories.md` file inside the selected vault.")
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
      }

    case .chatgpt, .claude, .gemini:
      VStack(alignment: .leading, spacing: 12) {
        Text("Omi will generate a Markdown memory pack, copy the upload prompt, reveal the file in Finder, and open \(destination.title).")
          .scaledFont(size: 13)
          .foregroundColor(OmiColors.textSecondary)

        Text(destination.manualPrompt)
          .scaledFont(size: 12)
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

    Button(model.isRunning ? actionTitle.running : actionTitle.idle) {
      Task {
        if let updatedStatus = await model.run(destination: destination) {
          statuses[destination] = updatedStatus
        }
      }
    }
    .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
    .disabled(model.isRunning)
  }

  private var actionTitle: (idle: String, running: String) {
    switch destination {
    case .notion:
      return ("Connect", "Syncing…")
    case .obsidian:
      return ("Connect", "Exporting…")
    case .chatgpt, .claude, .gemini:
      return ("Connect", "Preparing…")
    }
  }

  private func textField(_ title: String, text: Binding<String>, isSecure: Bool = false) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)

      Group {
        if isSecure {
          SecureField(title, text: text)
        } else {
          TextField(title, text: text)
        }
      }
      .textFieldStyle(.plain)
      .foregroundColor(OmiColors.textPrimary)
      .padding(.horizontal, 14)
      .padding(.vertical, 12)
      .background(
        RoundedRectangle(cornerRadius: 14, style: .continuous)
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
              .stroke(Color.white.opacity(0.08), lineWidth: 1)
          )
      )
    }
  }
}
