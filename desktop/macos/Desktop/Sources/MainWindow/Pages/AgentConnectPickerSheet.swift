import AppKit
import SwiftUI
import OmiTheme

/// Connect sheet for a grouped agent (Claude → Claude Code + Cloud, ChatGPT →
/// Codex + directory app). Both options are shown on screen at once as cards — no
/// picker — each with a prominent primary action and a quiet manual fallback.
/// The ChatGPT directory option is listed first so the one-click path leads.
struct ConnectDestinationSheet: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]
  let onDismiss: () -> Void

  /// Cloud/CLI pair for an anchor destination. ChatGPT leads with its approved
  /// directory listing; Claude keeps its established CLI-first order.
  static func group(for d: MemoryExportDestination) -> [MemoryExportDestination] {
    switch d {
    case .claude, .claudeCode: return [.claudeCode, .claude]
    case .chatgpt, .codex: return [.chatgpt, .codex]
    default: return [d]
    }
  }

  private var members: [MemoryExportDestination] { Self.group(for: destination) }

  private var groupName: String {
    switch destination {
    case .claude, .claudeCode: return "Claude"
    case .chatgpt, .codex: return "ChatGPT / Codex"
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
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          ConnectorBrandIcon(brand: groupBrand, size: 48, cornerRadius: 13)
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text("Connect \(groupName)")
              .scaledFont(size: OmiType.heading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text("Pick how to connect.")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
          Button(action: onDismiss) {
            Image(systemName: "xmark")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textTertiary)
              .frame(width: 28, height: 28)
              .background(Circle().fill(OmiColors.backgroundTertiary))
          }
          .buttonStyle(.plain)
          .accessibilityLabel("Close")
        }
        .padding(OmiSpacing.xxl)

        ScrollView {
          VStack(spacing: OmiSpacing.md) {
            ForEach(members, id: \.self) { d in
              ConnectOptionCard(destination: d, statuses: $statuses)
            }
          }
          .padding(.horizontal, OmiSpacing.xxl)
          .padding(.bottom, OmiSpacing.xxl)
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
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.md) {
        ConnectorBrandIcon(brand: destination.brand, size: 38, cornerRadius: OmiChrome.smallControlRadius)
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(optionLabel)
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(destination.description)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: 8)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
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
          ManualInstallationDisclosure(
            isExpanded: $showManual,
            title: destination == .chatgpt ? "Developer-mode fallback" : "Manual installation",
            fontSize: 12
          ) {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              if destination == .chatgpt {
                Text("Use this only when your workspace requires a developer-mode custom app.")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
                  .fixedSize(horizontal: false, vertical: true)
                  .frame(maxWidth: .infinity, alignment: .leading)
                manualBlock(chatGPTDeveloperModeText)
              } else {
                ForEach(Array(setup.steps.enumerated()), id: \.offset) { idx, step in
                  Text("\(idx + 1). \(step)")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                manualBlock(manualText(for: setup))
              }
            }
            .padding(.top, OmiSpacing.sm)
          }
        }
      }

      if let resultMessage {
        Text(resultMessage.text)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(resultMessage.foregroundColor)
      }
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
    .task {
      statuses[destination] = destination == .chatgpt
        ? await MemoryExportService.shared.refreshChatGPTDirectoryConnectionStatus()
        : await MemoryExportService.shared.status(for: destination)
      await prepareMCPKeyIfNeeded()
    }
    .onReceive(permissionRefreshTimer) { _ in
      refreshPermissionStateIfNeeded()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification))
    { _ in
      refreshPermissionStateIfNeeded()
      refreshChatGPTDirectoryConnectionIfNeeded()
    }
  }

  private func refreshPermissionStateIfNeeded() {
    guard MemoryExportExecutor.requiresAccessibilityPreflight(destination) else { return }
    permissionRefreshID += 1
  }

  private func refreshChatGPTDirectoryConnectionIfNeeded() {
    guard destination == .chatgpt else { return }
    Task {
      statuses[.chatgpt] = await MemoryExportService.shared.refreshChatGPTDirectoryConnectionStatus()
    }
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
        statuses[destination] = destination == .chatgpt
          ? await MemoryExportService.shared.refreshChatGPTDirectoryConnectionStatus()
          : await MemoryExportService.shared.status(for: destination)
      } catch {
        resultMessage = .failure(setupFailureMessage(for: error))
      }
      isRunning = false
    }
  }

  private func setupCompleteBlock(_ completion: MCPSetupCompletionSummary) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Image(systemName: "checkmark.seal.fill")
        .scaledFont(size: OmiType.subheading, weight: .semibold)
        .foregroundColor(OmiColors.success)
        .padding(.top, 1)
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(completion.title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(completion.subtitle)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(OmiColors.backgroundTertiary)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
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

  private var chatGPTDeveloperModeText: String {
    let clientID = destination.cloudOAuthClientID ?? ""
    let tokenAuthMethod = destination.cloudTokenAuthMethod ?? "none"
    return [
      "Name: Omi Memory",
      "Connection / server URL: \(MemoryExportDestination.mcpServerURL)",
      "Authentication: OAuth",
      "OAuth Client ID: \(clientID)",
      "OAuth Client Secret: leave blank",
      "Token auth method: \(tokenAuthMethod)",
      "Auth URL: \(MemoryExportDestination.mcpAuthorizeURL)",
      "Token URL: \(MemoryExportDestination.mcpTokenURL)",
    ].joined(separator: "\n")
  }

  private func manualBlock(_ text: String) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
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
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(.black)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.xs)
          .background(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous).fill(Color.white))
      }
      .buttonStyle(.plain)
    }
    .padding(OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous).fill(OmiColors.backgroundTertiary))
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
