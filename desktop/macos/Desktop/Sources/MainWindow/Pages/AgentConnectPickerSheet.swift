import SwiftUI

/// In-sheet "which one?" for grouped agents — Claude → Claude Code / Cloud,
/// ChatGPT → Codex / Cloud. Replaces the old standalone picker popup: the
/// choice now lives at the top of the connect sheet itself (no extra popup).
/// Claude Code / Codex are the default (prioritized); "Connect both" wires the
/// CLI and the cloud in one tap.
struct ConnectDestinationSheet: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]
  let onDismiss: () -> Void

  @State private var active: MemoryExportDestination
  @State private var bothStatus: String?

  init(
    destination: MemoryExportDestination,
    statuses: Binding<[MemoryExportDestination: MemoryExportStatus]>,
    onDismiss: @escaping () -> Void
  ) {
    self.destination = destination
    self._statuses = statuses
    self.onDismiss = onDismiss
    _active = State(initialValue: Self.group(for: destination).first ?? destination)
  }

  /// The grouped CLI+cloud pair for an anchor destination (CLI first).
  static func group(for d: MemoryExportDestination) -> [MemoryExportDestination] {
    switch d {
    case .claude, .claudeCode: return [.claudeCode, .claude]
    case .chatgpt, .codex: return [.codex, .chatgpt]
    default: return [d]
    }
  }

  private var members: [MemoryExportDestination] { Self.group(for: destination) }

  private func segmentLabel(_ d: MemoryExportDestination) -> String {
    switch d {
    case .claudeCode: return "Claude Code"
    case .codex: return "Codex"
    case .claude, .chatgpt: return "Cloud"
    default: return d.title
    }
  }

  var body: some View {
    if members.count > 1 {
      VStack(spacing: 0) {
        Picker("", selection: $active) {
          ForEach(members, id: \.self) { d in Text(segmentLabel(d)).tag(d) }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .padding(.horizontal, 24)
        .padding(.top, 18)

        HStack(spacing: 8) {
          Button("Connect both") { connectBoth() }
            .buttonStyle(.plain)
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.purplePrimary)
          if let bothStatus {
            Text(bothStatus)
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.success)
          }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 24)
        .padding(.top, 8)

        // Re-create the inner sheet when the selection flips so its per-client
        // model (key, steps, command) refreshes.
        MemoryExportDestinationSheet(destination: active, statuses: $statuses, onDismiss: onDismiss)
          .id(active)
      }
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
      bothStatus = "Both connected."
    }
  }
}
