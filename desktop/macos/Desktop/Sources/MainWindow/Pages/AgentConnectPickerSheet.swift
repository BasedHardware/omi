import SwiftUI

/// A tiny "which one do you want to connect?" picker that opens when a grouped
/// AI tile (Claude, ChatGPT) is tapped. Deliberately minimal text — just the
/// brand mark and one button per option. Claude Code / Codex are listed first
/// (the prioritized path); the cloud app second; "Both" optional.
struct AgentConnectPicker: Identifiable, Equatable {
  let id: String
  let brand: ConnectorBrand
  let title: String
  /// Ordered options shown as buttons. First = the prioritized (CLI) path.
  let options: [Option]
  /// If set, a "Connect both" button runs these in order.
  let both: [MemoryExportDestination]?

  struct Option: Identifiable, Equatable {
    let id: String
    let label: String
    let destination: MemoryExportDestination
  }

  static let claude = AgentConnectPicker(
    id: "claude",
    brand: .claude,
    title: "Connect Claude",
    options: [
      Option(id: "claudeCode", label: "Claude Code", destination: .claudeCode),
      Option(id: "claude", label: "Claude (cloud)", destination: .claude),
    ],
    both: [.claudeCode, .claude]
  )

  static let chatgpt = AgentConnectPicker(
    id: "chatgpt",
    brand: .chatgpt,
    title: "Connect ChatGPT",
    options: [
      Option(id: "codex", label: "Codex", destination: .codex),
      Option(id: "chatgpt", label: "ChatGPT (cloud)", destination: .chatgpt),
    ],
    both: [.codex, .chatgpt]
  )
}

struct AgentConnectPickerSheet: View {
  let picker: AgentConnectPicker
  /// Called with the destinations to connect, in order (one for a single
  /// option, two for "Both"). The presenter dismisses + routes to setup.
  let onChoose: ([MemoryExportDestination]) -> Void
  let onClose: () -> Void

  var body: some View {
    VStack(spacing: 16) {
      ConnectorBrandIcon(brand: picker.brand, size: 44, cornerRadius: 11)
        .padding(.top, 8)

      Text(picker.title)
        .scaledFont(size: 17, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      VStack(spacing: 10) {
        ForEach(picker.options) { option in
          pickerButton(option.label, primary: option.id == picker.options.first?.id) {
            onChoose([option.destination])
          }
        }
        if let both = picker.both {
          pickerButton("Connect both", primary: false) { onChoose(both) }
        }
      }

      Button("Cancel", action: onClose)
        .buttonStyle(.plain)
        .scaledFont(size: 13, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .padding(.top, 2)
    }
    .padding(24)
    .frame(width: 320)
  }

  private func pickerButton(_ label: String, primary: Bool, action: @escaping () -> Void)
    -> some View
  {
    Button(action: action) {
      Text(label)
        .scaledFont(size: 14, weight: .semibold)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 11)
        .foregroundColor(primary ? Color.black : OmiColors.textPrimary)
        .background(
          RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(primary ? Color.white : OmiColors.backgroundTertiary)
        )
    }
    .buttonStyle(.plain)
  }
}
