import OmiTheme
import SwiftUI

/// Quiet provenance for one summary section: a small control beside the section that opens the
/// transcript at every moment supporting it. It replaces an inline row of timestamps that sat
/// under each section's prose and competed with the summary itself.
struct ConversationSectionSources: View {
  let sourceIDs: [String]
  let onOpenSources: ([String]) -> Void
  @State private var hovering = false

  /// Cited IDs that resolve to a loaded transcript segment with a usable start, in citation order.
  static func resolve(_ ids: [String], segments: [TranscriptSegment]) -> [String] {
    ConversationSummarySelection.resolvableSourceIDs(ids, segments: segments).filter { id in
      guard let segment = segments.first(where: { $0.id == id || $0.backendId == id }) else { return false }
      return segment.start.isFinite && segment.start >= 0
    }
  }

  var body: some View {
    if !sourceIDs.isEmpty {
      Button {
        onOpenSources(sourceIDs)
      } label: {
        Image(systemName: "waveform")
          .imageScale(.small)
          .frame(width: 22, height: 22)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .foregroundColor(Ink.tertiary)
      // Present but recessive until the pointer is near; full contrast on hover.
      .opacity(hovering ? 1 : 0.55)
      .onHover { hovering = $0 }
      .help("Show in transcript")
      .accessibilityLabel("Show in transcript")
      .accessibilityIdentifier("conversation-summary-section-sources")
    }
  }
}
