import AppKit
import SwiftUI

/// Connect sheet for a grouped agent (Claude → Claude Code + Cloud, ChatGPT →
/// Codex + Cloud). Both options are shown on screen at once as cards — no
/// picker — each with its own "Do it for me". Claude Code / Codex (the CLI) is
/// listed first (prioritized); "Connect both" wires the CLI and the cloud.
struct ConnectDestinationSheet: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]
  let onDismiss: () -> Void

  @State private var bothStatus: String?

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
            Text("Pick one — or connect both.")
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
        }
        .padding(24)

        ScrollView {
          VStack(spacing: 12) {
            ForEach(members, id: \.self) { d in
              ConnectOptionCard(destination: d, statuses: $statuses)
            }

            Button(action: connectBoth) {
              Text("Connect both")
                .scaledFont(size: 14, weight: .semibold)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 11)
                .foregroundColor(OmiColors.textPrimary)
                .background(
                  RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)

            if let bothStatus {
              Text(bothStatus)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.success)
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

  private func connectBoth() {
    bothStatus = "Connecting…"
    Task { @MainActor in
      for d in members {
        _ = try? await MemoryExportExecutor.run(d)
      }
      bothStatus = "Both connected — follow along in the floating bar."
    }
  }
}

/// A single connect option (Claude Code, Cloud, …) shown as a card with its own
/// "Do it for me" and an optional copy-command fallback.
private struct ConnectOptionCard: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]

  @State private var isRunning = false
  @State private var resultMessage: String?
  @State private var mcpKey: String?

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
    destination.mcpExecuteKind == .autonomous ? "Do it for me" : "Open & copy key"
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

      HStack(spacing: 8) {
        Button(action: run) {
          Text(isRunning ? "Connecting…" : primaryLabel)
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(.black)
            .padding(.horizontal, 16)
            .padding(.vertical, 9)
            .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Color.white))
        }
        .buttonStyle(.plain)
        .disabled(isRunning)

        if let copyText = destination.mcpSetup(key: mcpKey ?? "YOUR_OMI_KEY")?.copyText {
          Button {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(copyText, forType: .string)
            resultMessage = "Command copied."
          } label: {
            Text("Copy command")
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
              .padding(.horizontal, 12)
              .padding(.vertical, 9)
              .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                  .fill(OmiColors.backgroundTertiary))
          }
          .buttonStyle(.plain)
        }
        Spacer(minLength: 0)
      }

      if let resultMessage {
        Text(resultMessage)
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(OmiColors.success)
      }
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
    )
    .task {
      if let stored = await MemoryExportService.shared.storedMCPKey() {
        mcpKey = stored
      } else {
        mcpKey = try? await MemoryExportService.shared.ensureMCPKey()
      }
    }
  }

  private func run() {
    isRunning = true
    Task { @MainActor in
      do {
        let outcome = try await MemoryExportExecutor.run(destination)
        switch outcome.mode {
        case .autonomous:
          resultMessage = "Omi is setting this up — follow along in the floating bar."
        case .assisted:
          resultMessage = "Opened \(destination.title) and copied your key."
        case .completed:
          resultMessage = outcome.taskTitle
        }
      } catch {
        resultMessage = error.localizedDescription
      }
      isRunning = false
    }
  }
}
