import SwiftUI

/// Small inline pill that surfaces *why* a conversation has no real title
/// (processing, locked, failed) instead of letting "Untitled" lie about all
/// three cases. Returns nil-equivalent (EmptyView) when the conversation is
/// in its normal titled state.
struct ConversationStatusBadge: View {
  let state: ConversationDisplayState

  var body: some View {
    switch state {
    case .processing:
      ProcessingPill()
    case .locked:
      Pill(
        icon: "lock.fill",
        text: "Locked",
        color: OmiColors.warning,
        help: "This conversation is locked until your subscription is active."
      )
    case .failed:
      Pill(
        icon: "exclamationmark.triangle.fill",
        text: "Failed",
        color: OmiColors.error,
        help: "Processing failed. Try Reprocess to rerun the title and summary."
      )
    case .untitledRecoverable:
      Pill(
        icon: "wand.and.stars",
        text: "Needs reprocess",
        color: OmiColors.info,
        help: "The transcript was captured but no title was generated. Try Reprocess."
      )
    case .titled, .untitledEmpty:
      // Titled state — no badge needed. Empty-state untitled also stays
      // quiet (probably ambient capture, no value in surfacing a pill).
      EmptyView()
    }
  }
}

/// Generic capsule pill with leading icon + label.
private struct Pill: View {
  let icon: String
  let text: String
  let color: Color
  let help: String

  var body: some View {
    HStack(spacing: 4) {
      Image(systemName: icon)
        .scaledFont(size: 9, weight: .semibold)
      Text(text)
        .scaledFont(size: 10, weight: .semibold)
    }
    .foregroundColor(color)
    .padding(.horizontal, 7)
    .padding(.vertical, 3)
    .background(
      Capsule(style: .continuous)
        .fill(color.opacity(0.16))
    )
    .help(help)
  }
}

/// Animated "Processing…" pill with a subtle pulsing dot.
private struct ProcessingPill: View {
  @State private var pulse = false

  var body: some View {
    HStack(spacing: 4) {
      Circle()
        .fill(OmiColors.purplePrimary)
        .frame(width: 6, height: 6)
        .opacity(pulse ? 0.4 : 1.0)
        .animation(
          .easeInOut(duration: 0.9).repeatForever(autoreverses: true),
          value: pulse
        )
      Text("Processing")
        .scaledFont(size: 10, weight: .semibold)
        .foregroundColor(OmiColors.purplePrimary)
    }
    .padding(.horizontal, 7)
    .padding(.vertical, 3)
    .background(
      Capsule(style: .continuous)
        .fill(OmiColors.purplePrimary.opacity(0.16))
    )
    .onAppear { pulse = true }
    .help("This conversation is still being processed. Title and summary will appear shortly.")
  }
}
