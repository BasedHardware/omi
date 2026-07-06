import AppKit
import SwiftUI

/// Connect sheet for a grouped agent (Claude → Claude Code + Cloud, ChatGPT →
/// Codex + Cloud). Both options are shown on screen at once as cards — no
/// picker — each with a prominent "Do it for me" primary and a quiet "Copy
/// command" secondary. Claude Code / Codex (the CLI) is listed first.
struct ConnectDestinationSheet: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]
  let onDismiss: () -> Void

  /// CLI+cloud pair for an anchor destination (CLI first).
  static func group(for d: MemoryExportDestination) -> [MemoryExportDestination] {
    switch d {
    case .claude, .claudeCode: return [.claudeCode, .claude]
    case .chatgpt, .codex: return [.codex, .chatgpt]
    default: return [d]
    }
  }

  private var members: [MemoryExportDestination] { Self.group(for: destination) }

  private var groupName: String {
    switch destination {
    case .claude, .claudeCode: return "Claude"
    case .chatgpt, .codex: return "ChatGPT"
    default: return destination.title
    }
  }

  private var groupBrand: ConnectorBrand {
    switch destination {
    case .claude, .claudeCode: return .claude
    case .chatgpt, .codex: return .chatgpt
    default: return destination.brand
    }
  }

  var body: some View {
    if members.count > 1 {
      VStack(alignment: .leading, spacing: 0) {
        HStack(alignment: .top, spacing: 14) {
          ConnectorBrandIcon(brand: groupBrand, size: 48, cornerRadius: 13)
          VStack(alignment: .leading, spacing: 3) {
            Text("Connect \(groupName)")
              .scaledFont(size: 20, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Pick how to connect.")
              .scaledFont(size: 13)
              .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
          Button(action: onDismiss) {
            Image(systemName: "xmark")
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(OmiColors.textTertiary)
              .frame(width: 28, height: 28)
              .background(Circle().fill(OmiColors.backgroundTertiary))
          }
          .buttonStyle(.plain)
          .accessibilityLabel("Close")
        }
        .padding(24)

        ScrollView {
          VStack(spacing: 12) {
            ForEach(members, id: \.self) { d in
              ConnectOptionCard(destination: d, statuses: $statuses)
            }
          }
          .padding(.horizontal, 24)
          .padding(.bottom, 24)
        }
      }
      .background(OmiColors.backgroundPrimary)
    } else {
      MemoryExportDestinationSheet(
        destination: destination, statuses: $statuses, onDismiss: onDismiss)
    }
  }

}

/// A single connect option (Claude Code, Cloud, …) shown as a card with its own
/// "Do it for me" and an optional copy-command fallback.
private struct ConnectOptionCard: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]

  @State private var isRunning = false
  @State private var resultMessage: ConnectOptionResultMessage?
  @State private var mcpKey: String?
  @State private var showManual = false
  @State private var permissionRefreshID = 0

  private let permissionRefreshTimer = Timer.publish(every: 1.0, on: .main, in: .common)
    .autoconnect()

  private var optionLabel: String {
    switch destination {
    case .claudeCode: return "Claude Code"
    case .claude: return "Claude (cloud)"
    case .codex: return "Codex"
    case .chatgpt: return "ChatGPT (cloud)"
    default: return destination.title
    }
  }

  private var primaryLabel: String {
    let presentation = connectionPresentation
    _ = permissionRefreshID
    return presentation.primaryActionTitle ?? "Connected"
  }

  private var connectionPresentation: MemoryExportConnectionPresentation {
    MemoryExportConnectionPresentation.make(
      destination: destination,
      status: statuses[destination],
      isRunning: isRunning,
      accessibilityPreflightMissing: MemoryExportExecutor.accessibilityPreflightMissing(
        for: destination)
    )
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 12) {
        ConnectorBrandIcon(brand: destination.brand, size: 38, cornerRadius: 10)
        VStack(alignment: .leading, spacing: 2) {
          Text(optionLabel)
            .scaledFont(size: 15, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(destination.description)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: 8)
      }

      VStack(alignment: .leading, spacing: 8) {
        if let completion = connectionPresentation.completion {
          setupCompleteBlock(completion)
        } else {
          // Primary action — the shared app pill (compact, white). Same style the
          // single-destination sheet uses, so the connect flow is consistent.
          Button(action: run) {
            ConnectionModalActionButton(
              title: isRunning ? "Connecting…" : primaryLabel,
              isConnected: isConnected
            )
          }
          .buttonStyle(.plain)
          .disabled(isRunning || isConnected)
        }

        // Secondary — full manual instructions in a quiet dropdown.
        if let setup = destination.mcpSetup(key: mcpKey ?? "YOUR_OMI_KEY") {
          ManualInstallationDisclosure(isExpanded: $showManual, fontSize: 12) {
            VStack(alignment: .leading, spacing: 8) {
              ForEach(Array(setup.steps.enumerated()), id: \.offset) { idx, step in
                Text("\(idx + 1). \(step)")
                  .scaledFont(size: 11)
                  .foregroundColor(OmiColors.textTertiary)
                  .fixedSize(horizontal: false, vertical: true)
                  .frame(maxWidth: .infinity, alignment: .leading)
              }
              manualBlock(manualText(for: setup))
            }
            .padding(.top, 8)
          }
        }
      }

      if let resultMessage {
        Text(resultMessage.text)
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(resultMessage.foregroundColor)
      }
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
    .task {
      statuses[destination] = await MemoryExportService.shared.status(for: destination)
      await prepareMCPKeyIfNeeded()
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

  private var isConnected: Bool {
    destination.hasLocallyVerifiableLiveSetup && statuses[destination]?.hasConnection == true
  }

  private func prepareMCPKeyIfNeeded() async {
    guard destination.requiresHostedMCPKeyForSetup else { return }
    if let stored = await MemoryExportService.shared.storedMCPKey() {
      mcpKey = stored
      return
    }
    do {
      mcpKey = try await MemoryExportService.shared.ensureMCPKey()
    } catch {
      resultMessage = .failure("Couldn't prepare your Omi key. Try again.")
    }
  }

  private func run() {
    isRunning = true
    Task { @MainActor in
      do {
        let outcome = try await MemoryExportExecutor.run(destination)
        switch outcome.mode {
        case .autonomous:
          resultMessage = .success("Omi is setting this up — follow along in the floating bar.")
        case .assisted:
          resultMessage = .success(outcome.taskTitle)
          // Assisted flow: the user pastes values by hand, so open the
          // step-by-step instructions instead of leaving them collapsed.
          if destination.assistedOverlayHint != nil {
            showManual = true
          }
        case .completed:
          resultMessage = .success(outcome.taskTitle)
        }
        statuses[destination] = await MemoryExportService.shared.status(for: destination)
      } catch {
        resultMessage = .failure(setupFailureMessage(for: error))
      }
      isRunning = false
    }
  }

  private func setupCompleteBlock(_ completion: MCPSetupCompletionSummary) -> some View {
    HStack(alignment: .top, spacing: 10) {
      Image(systemName: "checkmark.seal.fill")
        .scaledFont(size: 15, weight: .semibold)
        .foregroundColor(OmiColors.success)
        .padding(.top, 1)
      VStack(alignment: .leading, spacing: 4) {
        Text(completion.title)
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(completion.subtitle)
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(10)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(OmiColors.backgroundTertiary)
        .overlay(
          RoundedRectangle(cornerRadius: 10, style: .continuous)
            .stroke(OmiColors.success.opacity(0.22), lineWidth: 1))
    )
  }

  private func setupFailureMessage(for error: Error) -> String {
    if let executorError = error as? MemoryExportExecutor.ExecutorError {
      switch executorError {
      case .browserSetupRequired:
        return "Grant Accessibility, then try again."
      case .unsupported:
        return "\(optionLabel) setup isn't available yet."
      }
    }

    if let connectorError = error as? MemoryBankConnector.ConnectError {
      switch connectorError {
      case .notInstalled:
        return "\(optionLabel) isn't installed or available on this Mac."
      case .invalidConfig:
        return "Omi couldn't update \(optionLabel). Check its setup, then try again."
      }
    }

    return "Omi couldn't finish setup. Try again."
  }

  private func manualText(for setup: MCPSetup) -> String {
    if let copyText = setup.copyText {
      return copyText
    }
    if destination.requiresHostedMCPKeyForSetup {
      return "Server URL: \(setup.serverURL)\nKey: \(mcpKey ?? "YOUR_OMI_KEY")"
    }
    return "Server URL: \(setup.serverURL)"
  }

  private func manualBlock(_ text: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(text)
        .font(.system(size: 11, design: .monospaced))
        .foregroundColor(OmiColors.textSecondary)
        .textSelection(.enabled)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
      Button {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        resultMessage = .success("Copied.")
      } label: {
        Text("Copy")
          .scaledFont(size: 11, weight: .semibold)
          .foregroundColor(.black)
          .padding(.horizontal, 12)
          .padding(.vertical, 6)
          .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Color.white))
      }
      .buttonStyle(.plain)
    }
    .padding(10)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 8, style: .continuous).fill(OmiColors.backgroundTertiary))
  }
}

private enum ConnectOptionResultMessage {
  case success(String)
  case failure(String)

  var text: String {
    switch self {
    case .success(let text), .failure(let text):
      return text
    }
  }

  var foregroundColor: Color {
    switch self {
    case .success:
      return OmiColors.success
    case .failure:
      return OmiColors.warning
    }
  }
}
