import AppKit
import SwiftUI

struct ExportsSection: View {
  let statuses: [MemoryExportDestination: MemoryExportStatus]
  let onSelectDestination: (MemoryExportDestination) -> Void

  // Claude/Claude Code and ChatGPT/Codex are merged into one row each; tapping
  // opens the grouped sheet that shows both options. The CLI-only cases drop out.
  private var entries: [(destination: MemoryExportDestination, title: String?, subtitle: String?)] {
    MemoryExportDestination.allCases.compactMap { d in
      switch d {
      case .claudeCode, .codex:
        return nil
      case .claude:
        return (
          .claude, "Claude / Claude Code", "Claude Code (CLI) or Claude cloud — choose in setup."
        )
      case .chatgpt:
        return (.chatgpt, "ChatGPT / Codex", "Codex (CLI) or ChatGPT cloud — choose in setup.")
      default:
        return (d, nil, nil)
      }
    }
  }

  private func status(for destination: MemoryExportDestination) -> MemoryExportStatus {
    let fallback = MemoryExportStatus(
      exportedCount: 0,
      lastExportedAt: nil,
      detailText: nil,
      isConfigured: false,
      hasConnection: false)

    switch destination {
    case .claude:
      return aggregateStatus(for: [.claude, .claudeCode], fallback: fallback)
    case .chatgpt:
      return aggregateStatus(for: [.chatgpt, .codex], fallback: fallback)
    default:
      return statuses[destination] ?? fallback
    }
  }

  private func aggregateStatus(
    for destinations: [MemoryExportDestination],
    fallback: MemoryExportStatus
  ) -> MemoryExportStatus {
    let values = destinations.map { statuses[$0] ?? fallback }
    return MemoryExportStatus(
      exportedCount: values.map(\.exportedCount).max() ?? 0,
      lastExportedAt: values.compactMap(\.lastExportedAt).max(),
      detailText: values.compactMap(\.detailText).first,
      isConfigured: values.contains(where: \.hasConnection),
      hasConnection: values.contains(where: \.hasConnection)
    )
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("Exports")
        .scaledFont(size: 18, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      VStack(spacing: 0) {
        ForEach(Array(entries.enumerated()), id: \.element.destination.id) { index, entry in
          if index > 0 {
            Divider()
              .background(OmiColors.backgroundTertiary)
          }
          MemoryExportRow(
            destination: entry.destination,
            titleOverride: entry.title,
            subtitleOverride: entry.subtitle,
            status: status(for: entry.destination)
          ) {
            onSelectDestination(entry.destination)
          }
        }
      }
    }
  }
}

private struct AgentSetupActionButtonStyle: ButtonStyle {
  enum Kind {
    case primary
    case secondary
  }

  let kind: Kind

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.system(size: 13, weight: .semibold))
      .foregroundColor(kind == .primary ? .black : OmiColors.textPrimary)
      .lineLimit(1)
      .labelStyle(.titleAndIcon)
      .padding(.horizontal, kind == .primary ? 14 : 12)
      .padding(.vertical, 8)
      .frame(minHeight: 36)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(kind == .primary ? Color.white : OmiColors.backgroundTertiary)
      )
      .overlay(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .stroke(Color.white.opacity(kind == .primary ? 0 : 0.08), lineWidth: 1)
      )
      .opacity(configuration.isPressed ? 0.9 : 1)
      .scaleEffect(configuration.isPressed ? 0.985 : 1)
      .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
  }
}

private struct MemoryExportRow: View {
  let destination: MemoryExportDestination
  var titleOverride: String? = nil
  var subtitleOverride: String? = nil
  let status: MemoryExportStatus
  let action: () -> Void

  @State private var isHovering = false

  private var actionTitle: String {
    if destination.supportsAgentSetup {
      return showsConnectedState ? "Connected" : "Connect"
    }
    if destination.supportsMCP {
      return showsConnectedState ? "Connected" : "Connect"
    }
    switch destination {
    case .obsidian:
      return status.isConfigured ? "Sync" : "Connect"
    case .notion, .chatgpt, .claude, .gemini, .agents, .claudeCode, .codex, .openclaw, .hermes:
      return "Open"
    }
  }

  private var showsConnectedState: Bool {
    guard destination.supportsMCP || destination.supportsAgentSetup else { return false }
    return status.hasConnection
  }

  var body: some View {
    Button(action: action) {
      HStack(spacing: 12) {
        ConnectorBrandIcon(brand: destination.brand, size: 34, cornerRadius: 9)

        VStack(alignment: .leading, spacing: 2) {
          Text(titleOverride ?? destination.title)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)

          Text(subtitleOverride ?? destination.description)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.tail)
        }

        Spacer(minLength: 12)

        ImportConnectorActionButton(
          title: actionTitle, isConnected: showsConnectedState)
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
  @Published var isTestingAgentConnection = false

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

  func createNewAgentConnectionKey() async {
    errorMessage = nil
    statusMessage = nil
    isLoadingMCPKey = true
    defer { isLoadingMCPKey = false }

    do {
      let key = try await MemoryExportService.shared.createNewMCPKey()
      _ = LocalAgentAPISettings.createNewToken()
      mcpKey = key
      statusMessage = "New key created. Copy the prompt again when you're ready."
    } catch {
      errorMessage = "Couldn't create a new connection key: \(error.localizedDescription)"
    }
  }

  func testAgentConnection() async {
    errorMessage = nil
    statusMessage = nil
    isTestingAgentConnection = true
    defer { isTestingAgentConnection = false }

    do {
      let key = try await MemoryExportService.shared.ensureMCPKey()
      let localToken = LocalAgentAPISettings.enable()
      mcpKey = key
      let result = try await MemoryExportService.shared.testAgentConnections(
        hostedKey: key,
        localToken: localToken)
      statusMessage = result.summary
    } catch {
      errorMessage = "Omi couldn't test the connection: \(error.localizedDescription)"
    }
  }

  func copyToPasteboard(_ text: String, label: String) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
    statusMessage = "\(label) copied."
  }

  func copyAgentSetupPrompt() async -> MemoryExportStatus? {
    errorMessage = nil
    statusMessage = nil
    isLoadingMCPKey = true
    defer { isLoadingMCPKey = false }

    do {
      let key = try await MemoryExportService.shared.ensureMCPKey()
      let localToken = LocalAgentAPISettings.enable()
      mcpKey = key
      copyToPasteboard(
        MemoryExportService.omiAgentSetupPrompt(
          hostedKey: key,
          localURL: LocalAgentAPISettings.serverURL,
          localToken: localToken),
        label: "Agent prompt")
      statusMessage =
        "Prompt copied. Only share it with an agent you trust; it includes Omi access keys."
      return await MemoryExportService.shared.status(for: .agents)
    } catch {
      errorMessage = "Couldn't create the prompt: \(error.localizedDescription)"
      return nil
    }
  }

  func open(_ url: URL) {
    NSWorkspace.shared.open(url)
  }

  @Published var isExecuting = false

  /// Hand the whole setup to Omi: create a task and run it through the standard
  /// execute flow (TasksStore.createTask + AgentPillsManager.spawn) — the same path
  /// the floating-bar "Execute" button uses. No new execution flow.
  func executeWithOmi(destination: MemoryExportDestination) async {
    errorMessage = nil
    isExecuting = true
    defer { isExecuting = false }

    do {
      let outcome = try await MemoryExportExecutor.run(destination)
      mcpKey = await MemoryExportService.shared.storedMCPKey()
      switch outcome.mode {
      case .autonomous:
        statusMessage = "Omi is setting this up — follow along in the floating bar."
      case .assisted:
        statusMessage = outcome.taskTitle
      case .completed:
        // Deterministic local write — show the result directly.
        statusMessage = outcome.taskTitle
      }
    } catch {
      errorMessage = error.localizedDescription
    }
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

      case .agents, .claudeCode, .codex, .openclaw, .hermes:
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
  @State private var showManualSetup = false
  @State private var permissionRefreshID = 0

  private let permissionRefreshTimer = Timer.publish(every: 1.0, on: .main, in: .common)
    .autoconnect()

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

      // Scrollable so the full connector flow (Execute + live-connection steps +
      // memory pack) never clips inside the fixed-height sheet.
      ScrollView {
        VStack(alignment: .leading, spacing: 18) {
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
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
    .padding(24)
    .background(OmiColors.backgroundPrimary)
    .task {
      await model.loadConfiguration()
      statuses[destination] = await MemoryExportService.shared.status(for: destination)
      if destination.supportsMCP && destination.requiresHostedMCPKeyForSetup && model.mcpKey == nil {
        await model.generateMCPKey()
      }
    }
    .onReceive(permissionRefreshTimer) { _ in
      refreshPermissionStateIfNeeded()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification))
    { _ in
      refreshPermissionStateIfNeeded()
    }
  }

  private func refreshPermissionStateIfNeeded() {
    guard MemoryExportExecutor.requiresAccessibilityPreflight(destination) else { return }
    permissionRefreshID += 1
  }

  @ViewBuilder
  private var content: some View {
    VStack(alignment: .leading, spacing: 18) {
      if destination.supportsAgentSetup {
        agentSetupSection
      } else if destination.supportsMCP {
        // Lead with the one action — "Do it for me". Everything manual (live
        // MCP fields, memory pack) is tucked behind a collapsed disclosure so
        // the default view stays simple.
        executeBlock
        manualSetupDisclosure
      } else if destination.supportsMemoryPack {
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

  @ViewBuilder
  private var manualSetupDisclosure: some View {
    ManualInstallationDisclosure(isExpanded: $showManualSetup, fontSize: 13) {
      VStack(alignment: .leading, spacing: 18) {
        methodHeader(
          icon: "bolt.fill",
          title: "Live connection",
          tag: "AUTOMATIC",
          tagColor: OmiColors.success,
          subtitle: "Set it once — \(destination.title) reads your memories live and stays in sync."
        )
        mcpSection

        if destination.supportsMemoryPack {
          Divider()
            .background(OmiColors.backgroundTertiary)
            .padding(.vertical, 2)
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
      .padding(.top, 10)
    }
  }

  private var agentSetupSection: some View {
    VStack(alignment: .leading, spacing: 16) {
      agentSetupHeader

      VStack(alignment: .leading, spacing: 8) {
        agentSetupBullet("Omi creates fresh connection keys for this prompt.")
        agentSetupBullet(
          "Your agent can read synced memories and conversations, then use this Mac for screen history, screenshots, recaps, files, and tasks."
        )
        agentSetupBullet(
          "The included Omi guide helps your agent choose the right context and ask before changing memories."
        )
      }

      HStack(spacing: 10) {
        Button {
          Task {
            if let updatedStatus = await model.copyAgentSetupPrompt() {
              statuses[destination] = updatedStatus
            }
          }
        } label: {
          Label(model.isLoadingMCPKey ? "Preparing…" : "Copy prompt", systemImage: "sparkles")
        }
        .buttonStyle(AgentSetupActionButtonStyle(kind: .primary))
        .disabled(model.isLoadingMCPKey)

        Button {
          Task { await model.testAgentConnection() }
        } label: {
          Label(model.isTestingAgentConnection ? "Testing…" : "Test", systemImage: "checkmark.seal")
        }
        .buttonStyle(AgentSetupActionButtonStyle(kind: .secondary))
        .disabled(model.isLoadingMCPKey || model.isTestingAgentConnection)
        .help("Test hosted and local Omi access")

        Button {
          Task {
            await model.createNewAgentConnectionKey()
            statuses[destination] = await MemoryExportService.shared.status(for: destination)
          }
        } label: {
          Label("New key", systemImage: "key")
        }
        .buttonStyle(AgentSetupActionButtonStyle(kind: .secondary))
        .disabled(model.isLoadingMCPKey || model.isTestingAgentConnection)
        .help("Create fresh hosted and local connection keys")
      }
    }
  }

  private var agentSetupHeader: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 9) {
        Text("Let your agent do it")
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("MCP + CLI")
          .scaledFont(size: 9, weight: .bold)
          .foregroundColor(OmiColors.success)
          .padding(.horizontal, 7)
          .padding(.vertical, 2)
          .background(Capsule().fill(OmiColors.success.opacity(0.15)))
      }
      Text(
        "Copy one setup prompt for your agent. It connects Omi memories through MCP, turns on local Desktop access through the Omi CLI, and includes a short Omi guide the agent can keep."
      )
      .scaledFont(size: 12)
      .foregroundColor(OmiColors.textTertiary)
      .fixedSize(horizontal: false, vertical: true)
    }
  }

  private func agentSetupBullet(_ text: String) -> some View {
    HStack(alignment: .top, spacing: 8) {
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.success)
        .padding(.top, 1)
      Text(text)
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var executeButtonTitle: String {
    let presentation = executePresentation
    _ = permissionRefreshID
    return presentation.primaryActionTitle ?? "Connected"
  }

  private var executePresentation: MemoryExportConnectionPresentation {
    MemoryExportConnectionPresentation.make(
      destination: destination,
      status: statuses[destination],
      isRunning: model.isExecuting,
      accessibilityPreflightMissing: MemoryExportExecutor.accessibilityPreflightMissing(
        for: destination)
    )
  }

  private var executeBlockSubtitle: String {
    switch destination.mcpExecuteKind {
    case .localAutonomous:
      return
        "Omi sets up \(destination.title) for you — it runs as an Omi task you can watch in the floating bar. If it gets stuck, use the manual steps below."
    case .browserAutonomous:
      if MemoryExportExecutor.accessibilityPreflightMissing(for: destination) {
        return
          "Omi needs Accessibility permission to use your signed-in browser for \(destination.title). If you prefer not to grant it, use the manual steps below."
      } else {
        return
          "Omi uses your signed-in browser to set up \(destination.title). If sign-in or permissions block it, Omi will tell you exactly where it stopped."
      }
    case .assisted:
      if destination.assistedOverlayHint != nil {
        return
          "Omi opens \(destination.title) and shows an on-screen card — copy each value with one click and paste it into the form."
      }
      return
        "Omi opens \(destination.title) and copies your key, then you confirm the quick steps below."
    }
  }

  /// "Execute" — hands the whole setup to Omi to run as a task.
  private var executeBlock: some View {
    VStack(alignment: .leading, spacing: 8) {
      if let completion = executePresentation.completion {
        setupCompleteBlock(completion)
      } else {
        HStack(spacing: 8) {
          Image(systemName: "sparkles")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
          Text("Let Omi do it")
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("FASTEST")
            .scaledFont(size: 9, weight: .bold)
            .foregroundColor(OmiColors.success)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(Capsule().fill(OmiColors.success.opacity(0.15)))
        }
        Text(executeBlockSubtitle)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)

        Button {
          Task {
            await model.executeWithOmi(destination: destination)
            statuses[destination] = await MemoryExportService.shared.status(for: destination)
            // Assisted flow: the user pastes values by hand, so surface the
            // field-by-field steps instead of leaving them collapsed.
            if destination.mcpExecuteKind == .assisted, destination.assistedOverlayHint != nil {
              showManualSetup = true
            }
          }
        } label: {
          ConnectionModalActionButton(
            title: model.isExecuting ? "Starting Omi…" : executeButtonTitle,
            isConnected: isConnected
          )
        }
        .buttonStyle(.plain)
        .disabled(model.isExecuting || isConnected)
      }
    }
  }

  private func setupCompleteBlock(_ completion: MCPSetupCompletionSummary) -> some View {
    HStack(alignment: .top, spacing: 10) {
      Image(systemName: "checkmark.seal.fill")
        .scaledFont(size: 16, weight: .semibold)
        .foregroundColor(OmiColors.success)
        .padding(.top, 1)
      VStack(alignment: .leading, spacing: 4) {
        Text(completion.title)
          .scaledFont(size: 15, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(completion.subtitle)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .stroke(OmiColors.success.opacity(0.22), lineWidth: 1))
    )
  }

  private var isConnected: Bool {
    guard destination.hasLocallyVerifiableLiveSetup else { return false }
    return statuses[destination]?.hasConnection == true
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
      if destination == .claude {
        claudeConnectorFields
      } else {
        mcpCodeRow(
          label: "Server URL", value: MemoryExportDestination.mcpServerURL, copyLabel: "Server URL")

        if destination.requiresHostedMCPKeyForSetup {
          mcpKeyRow
        }
      }

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
  private var claudeConnectorFields: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("Copy these fields into Claude's Add custom connector form.")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)

      mcpCodeRow(label: "Name", value: "Omi Memory", copyLabel: "Name")

      mcpCodeRow(
        label: "Remote MCP server URL",
        value: MemoryExportDestination.mcpServerURL,
        copyLabel: "Remote MCP server URL"
      )

      Text("Advanced settings")
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .padding(.top, 2)

      mcpCodeRow(
        label: "OAuth Client ID",
        value: destination.cloudOAuthClientID ?? "",
        copyLabel: "OAuth Client ID")

      Text("Leave OAuth Client Secret blank.")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
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

    case .agents, .claudeCode, .codex, .openclaw, .hermes:
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
    case .agents, .claudeCode, .codex, .openclaw, .hermes:
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
