import OmiTheme
import SwiftUI

/// The greeting block at the top of the Home stage: a serif salutation and a
/// single ambient proof sub-line summarizing what Omi delivered today.
/// Capture/listening status intentionally lives only in the header chips —
/// this line is content, not status.
struct HomeGreetingView: View {
  let greeting: String
  let segments: [HomeGreetingComposer.Segment]
  let onOpen: (HomeGreetingComposer.SegmentDestination) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      Text(greeting)
        .font(.system(size: 30, weight: .medium, design: .serif))
        .foregroundStyle(HomeStagePalette.ink)
        .lineLimit(1)
        .minimumScaleFactor(0.7)

      if !segments.isEmpty {
        proofLine
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("home-greeting")
  }

  private var proofLine: some View {
    HStack(spacing: 0) {
      ForEach(Array(segments.enumerated()), id: \.offset) { index, segment in
        if index > 0 {
          Text(separator(before: segment))
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundStyle(HomeStagePalette.faint)
        }
        HomeGreetingSegmentView(segment: segment, onOpen: onOpen)
      }
    }
    .lineLimit(1)
  }

  /// Countable segments join with a middle dot; plain-text segments (e.g.
  /// "today", "Quiet so far today —") join with a space.
  private func separator(before segment: HomeGreetingComposer.Segment) -> String {
    segment.destination == nil ? " " : "  ·  "
  }
}

private struct HomeGreetingSegmentView: View {
  let segment: HomeGreetingComposer.Segment
  let onOpen: (HomeGreetingComposer.SegmentDestination) -> Void

  @State private var isHovering = false

  var body: some View {
    if let destination = segment.destination {
      Button {
        onOpen(destination)
      } label: {
        Text(segment.text)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(isHovering ? HomeStagePalette.ink : HomeStagePalette.secondary)
          .underline(isHovering, color: HomeStagePalette.muted)
      }
      .buttonStyle(.plain)
      .onHover { isHovering = $0 }
    } else {
      Text(segment.text)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundStyle(HomeStagePalette.muted)
    }
  }
}
