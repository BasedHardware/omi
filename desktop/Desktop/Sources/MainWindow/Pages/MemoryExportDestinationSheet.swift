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

      VStack(spacing: 0) {
        ForEach(Array(destinations.enumerated()), id: \.element.id) { index, destination in
          if index > 0 {
            Divider()
              .background(OmiColors.backgroundTertiary)
          }
          MemoryExportRow(
            destination: destination,
            status: statuses[destination]
              ?? MemoryExportStatus(
                exportedCount: 0, lastExportedAt: nil, detailText: nil, isConfigured: false)
          ) {
            onSelectDestination(destination)
          }
        }
      }
      .background(OmiColors.backgroundPrimary)
      .cornerRadius(12)
      .overlay(
        RoundedRectangle(cornerRadius: 12)
          .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
      )
    }
  }
}

private struct MemoryExportRow: View {
  let destination: MemoryExportDestination
  let status: MemoryExportStatus
  let action: () -> Void

  @State private var isHovering = false

  private var actionTitle: String {
    if destination.supportsMCP {
      return status.isConfigured ? "Manage" : "Connect"
    }
    switch destination {
    case .obsidian:
      return status.isConfigured ? "Sync" : "Connect"
    case .notion, .chatgpt, .claude, .gemini, .claudeCode, .codex:
      return "Open"
    }
  }

  var body: some View {
    Button(action: action) {
      HStack(spacing: 12) {
        ConnectorBrandIcon(brand: destination.brand, size: 34, cornerRadius: 9)

        VStack(alignment: .leading, spacing: 2) {
          Text(destination.title)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)

          Text(destination.description)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.tail)
        }

        Spacer(minLength: 12)

        ImportConnectorActionButton(
          title: actionTitle, isConnected: status.isConfigured || status.exportedCount > 0)
      }
      .padding(.horizontal, 14)
      .padding(.vertical, 11)
      .background(isHovering ? OmiColors.backgroundSecondary : Color.clear)
      .contentShape(Rectangle())
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
  @Published var mcpKey: String?
  @Published var isLoadingMCPKey = false

  func loadConfiguration() async {
    obsidianVaultPath = await MemoryExportService.shared.obsidianVaultPath()
    mcpKey = await MemoryExportService.shared.storedMCPKey()
  }

  func generateMCPKey() async {
    errorMessage = nil
    isLoadingMCPKey = true
    defer { isLoadingMCPKey = false }
    do {
      mcpKey = try await MemoryExportService.shared.ensureMCPKey()
    } catch {
      errorMessage = "Couldn't create an MCP key: \(error.localizedDescription)"
    }
  }

  func copyToPasteboard(_ text: String, label: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
    statusMessage = "\(label) copied."
  }

  func open(_ url: URL) {
    NSWorkspace.shared.open(url)
  }

  func run(destination: MemoryExportDestination) async -> MemoryExportStatus? {
    errorMessage = nil
    statusMessage = nil
    isRunning = true
    defer { isRunning = false }

    do {
      switch destination {
      case .notion:
        let result = try await MemoryExportService.shared.prepareManualExport(for: destination)
        await MainActor.run {
          applyClipboard(from: result)
          revealExportFile(from: result)
          openDestination(for: destination, url: result.destinationURL)
        }
        statusMessage = "Copied \(result.memoryCount.formatted()) memories for Notion."

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
          revealExportFile(from: result)
          openDestination(for: destination, url: result.destinationURL)
        }
        statusMessage = "Wrote \(result.memoryCount.formatted()) memories into Obsidian."

      case .chatgpt, .claude, .gemini:
        let result = try await MemoryExportService.shared.prepareManualExport(for: destination)
        await MainActor.run {
          applyClipboard(from: result)
          revealExportFile(from: result)
          openDestination(for: destination, url: result.destinationURL)
        }
        statusMessage = "Memory pack ready for \(destination.title). Prompt and export copied."

      case .claudeCode, .codex:
        // MCP-only destinations have no memory-pack run step.
        return nil
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

  private func applyClipboard(from result: MemoryExportResult) {
    guard let clipboardText = result.clipboardText, !clipboardText.isEmpty else { return }
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(clipboardText, forType: .string)
  }

  private func revealExportFile(from result: MemoryExportResult) {
    guard let fileURL = result.fileURL else { return }
    NSWorkspace.shared.activateFileViewerSelecting([fileURL])
  }

  private func openDestination(for destination: MemoryExportDestination, url: URL?) {
    guard let url else { return }

    if let appURL = destination.brand.installedApplicationURL {
      let configuration = NSWorkspace.OpenConfiguration()
      configuration.activates = true

      NSWorkspace.shared.open([url], withApplicationAt: appURL, configuration: configuration) {
        _, error in
        if let error {
          log(
            "MemoryExportDestinationSheetModel: Failed opening \(destination.title) with installed app: \(error.localizedDescription)"
          )
          Task { @MainActor in
            self.openInDefaultHandler(url)
          }
        }
      }
      return
    }

    openInDefaultHandler(url)
  }

  private func openInDefaultHandler(_ url: URL) {
    let configuration = NSWorkspace.OpenConfiguration()
    configuration.activates = true

    if let appURL = NSWorkspace.shared.urlForApplication(toOpen: url) {
      NSWorkspace.shared.open([url], withApplicationAt: appURL, configuration: configuration) {
        _, error in
        if let error {
          log(
            "MemoryExportDestinationSheetModel: Failed opening \(url.absoluteString): \(error.localizedDescription)"
          )
          NSWorkspace.shared.open(url)
        }
      }
      return
    }

    NSWorkspace.shared.open(url)
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
    VStack(alignment: .leading, spacing: 18) {
      if destination.supportsMCP {
        methodHeader(
          icon: "bolt.fill",
          title: "Live connection",
          tag: "AUTOMATIC",
          tagColor: OmiColors.success,
          subtitle: "Set it once — \(destination.title) reads your memories live and stays in sync."
        )
        mcpSection
      }

      if destination.supportsMemoryPack {
        if destination.supportsMCP {
          Divider()
            .background(OmiColors.backgroundTertiary)
            .padding(.vertical, 2)
        }
        methodHeader(
          icon: "doc.on.clipboard.fill",
          title: "Memory pack",
          tag: "MANUAL",
          tagColor: OmiColors.textTertiary,
          subtitle: "Copy a one-time snapshot and paste it in yourself. Won't update on its own."
        )
        packSection
        packActionButton
      }
    }
  }

  /// Labeled header that makes the automatic (MCP) vs manual (pack) choice obvious.
  private func methodHeader(
    icon: String, title: String, tag: String, tagColor: Color, subtitle: String
  ) -> some View {
    VStack(alignment: .leading, spacing: 4) {
      HStack(spacing: 8) {
        Image(systemName: icon)
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(tagColor)
        Text(title)
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(tag)
          .scaledFont(size: 9, weight: .bold)
          .foregroundColor(tagColor)
          .padding(.horizontal, 7)
          .padding(.vertical, 2)
          .background(
            Capsule().fill(tagColor.opacity(0.15))
          )
      }
      Text(subtitle)
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  // MARK: - MCP connection

  @ViewBuilder
  private var mcpSection: some View {
    let setup = destination.mcpSetup(key: model.mcpKey ?? "YOUR_OMI_KEY")
    VStack(alignment: .leading, spacing: 12) {
      mcpCodeRow(
        label: "Server URL", value: MemoryExportDestination.mcpServerURL, copyLabel: "Server URL")

      mcpKeyRow

      if let setup, let copyText = setup.copyText, let copyTitle = setup.copyTitle {
        mcpSnippet(copyText, title: copyTitle, enabled: model.mcpKey != nil)
      }

      if let setup {
        VStack(alignment: .leading, spacing: 6) {
          ForEach(Array(setup.steps.enumerated()), id: \.offset) { index, step in
            HStack(alignment: .top, spacing: 8) {
              Text("\(index + 1).")
                .scaledFont(size: 12, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
              Text(step)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
        .padding(.top, 2)

        if let openURL = setup.openURL, let openTitle = setup.openTitle {
          Button(openTitle) { model.open(openURL) }
            .buttonStyle(.plain)
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
        }
      }
    }
  }

  @ViewBuilder
  private var mcpKeyRow: some View {
    if let key = model.mcpKey {
      mcpCodeRow(label: "Your key", value: key, copyLabel: "Key", secure: true)
    } else {
      Button(model.isLoadingMCPKey ? "Generating…" : "Generate connection key") {
        Task { await model.generateMCPKey() }
      }
      .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
      .disabled(model.isLoadingMCPKey)
    }
  }

  private func mcpCodeRow(label: String, value: String, copyLabel: String, secure: Bool = false)
    -> some View
  {
    VStack(alignment: .leading, spacing: 6) {
      Text(label)
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
      HStack(spacing: 8) {
        Text(secure ? String(repeating: "•", count: min(value.count, 28)) : value)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
          .truncationMode(.middle)
          .frame(maxWidth: .infinity, alignment: .leading)
        Button("Copy") { model.copyToPasteboard(value, label: copyLabel) }
          .buttonStyle(.plain)
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 10)
      .background(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
              .stroke(Color.white.opacity(0.08), lineWidth: 1))
      )
    }
  }

  private func mcpSnippet(_ text: String, title: String, enabled: Bool) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(text)
        .scaledFont(size: 11)
        .foregroundColor(OmiColors.textSecondary)
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .fill(OmiColors.backgroundSecondary)
            .overlay(
              RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1))
        )
      Button(title) { model.copyToPasteboard(text, label: title) }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        .disabled(!enabled)
    }
  }

  // MARK: - Memory pack

  @ViewBuilder
  private var packSection: some View {
    switch destination {
    case .notion:
      VStack(alignment: .leading, spacing: 12) {
        Text(
          "Omi copies a ready-to-paste Markdown page, saves a local backup, and opens Notion so you can drop it where you want."
        )
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
      }

    case .obsidian:
      VStack(alignment: .leading, spacing: 12) {
        selectedLocationCard(
          title: model.obsidianVaultPath.isEmpty ? "No vault selected yet" : "Selected vault",
          value: model.obsidianVaultPath.isEmpty
            ? "Pick your Obsidian vault once, then Omi will keep refreshing `Omi/Memories.md`."
            : model.obsidianVaultPath
        )

        Button(model.obsidianVaultPath.isEmpty ? "Choose vault" : "Change vault") {
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
        Text(
          "Omi will generate a Markdown memory pack, copy the prompt and export together, reveal the file in Finder, and open \(destination.title)."
        )
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

    case .claudeCode, .codex:
      EmptyView()
    }
  }

  private var packActionButton: some View {
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
      return ("Copy & open", "Preparing…")
    case .obsidian:
      return (model.obsidianVaultPath.isEmpty ? "Choose vault" : "Export", "Exporting…")
    case .chatgpt, .claude, .gemini:
      return ("Copy & open", "Preparing…")
    case .claudeCode, .codex:
      return ("Copy", "…")
    }
  }

  private func textField(_ title: String, text: Binding<String>, isSecure: Bool = false)
    -> some View
  {
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

  private func selectedLocationCard(title: String, value: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)

      Text(value)
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textPrimary)
        .frame(maxWidth: .infinity, alignment: .leading)
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
