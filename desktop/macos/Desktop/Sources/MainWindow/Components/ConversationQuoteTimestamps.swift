import OmiTheme
import SwiftUI

struct ConversationQuoteTimestamp: Identifiable, Equatable {
  let id: String
  let start: Double

  var timestamp: String { OmiDateFormat.offset(start) }

  var accessibilityLabel: String {
    let formatter = DateComponentsFormatter()
    formatter.allowedUnits = [.hour, .minute, .second]
    formatter.unitsStyle = .full
    let duration = formatter.string(from: start.rounded(.down)) ?? timestamp
    return String(localized: "Jump to \(duration)")
  }

  static func resolve(_ ids: [String], segments: [TranscriptSegment]) -> [Self] {
    ConversationSummarySelection.resolvableSourceIDs(ids, segments: segments).compactMap { id in
      guard let segment = segments.first(where: { $0.id == id || $0.backendId == id }),
        segment.start.isFinite, segment.start >= 0, segment.start < Double(Int.max)
      else { return nil }
      return Self(id: id, start: segment.start)
    }
  }
}

struct ConversationQuoteTimestamps: View {
  let sources: [ConversationQuoteTimestamp]
  let onOpenSource: (String) -> Void
  @State private var expanded = false

  var body: some View {
    if !sources.isEmpty {
      FlowLayout(spacing: OmiSpacing.xs) {
        ForEach(Array((expanded ? sources : Array(sources.prefix(3))).enumerated()), id: \.element.id) {
          index, source in
          HStack(spacing: OmiSpacing.xs) {
            if index == 0 {
              Image(systemName: "play.fill")
                .imageScale(.small)
                .accessibilityHidden(true)
            } else {
              Text("·").accessibilityHidden(true)
            }
            Button(source.timestamp) { onOpenSource(source.id) }
              .buttonStyle(.plain)
              .accessibilityLabel(source.accessibilityLabel)
          }
        }
        if !expanded && sources.count > 3 {
          HStack(spacing: OmiSpacing.xs) {
            Text("·").accessibilityHidden(true)
            Button("+\(sources.count - 3) more") { expanded = true }
              .buttonStyle(.plain)
          }
        }
      }
      .scaledFont(size: OmiType.caption)
      .monospacedDigit()
      .foregroundColor(Ink.tertiary)
      .accessibilityElement(children: .contain)
      .accessibilityIdentifier("conversation-summary-section-sources")
    }
  }
}
