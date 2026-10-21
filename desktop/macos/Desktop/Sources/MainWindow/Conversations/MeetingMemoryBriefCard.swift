import OmiTheme
import SwiftUI

/// Read-only context on the Conversations page. It never enters Chat or sends a notification.
struct MeetingMemoryBriefCard: View {
  let brief: MeetingMemoryBrief
  let onOpenSource: (MeetingMemoryBriefFact) -> Void
  let onDismiss: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.md) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Before \(brief.title)")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(Ink.primary)
            .lineLimit(2)

          Text("\(OmiDateFormat.timestamp(brief.startsAt)) · From \(brief.sourceConversationTitle)")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(1)
        }

        Spacer(minLength: OmiSpacing.sm)

        OmiIconButton("xmark", help: "Dismiss meeting brief", size: .compact, action: onDismiss)
          .accessibilityIdentifier("meeting-brief-dismiss")
      }

      ForEach(brief.facts) { fact in
        Button {
          onOpenSource(fact)
        } label: {
          HStack(alignment: .top, spacing: OmiSpacing.sm) {
            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text(fact.kind.label)
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundColor(Ink.secondary)
              Text(fact.text)
                .scaledFont(size: OmiType.body)
                .foregroundColor(Ink.primary)
                .multilineTextAlignment(.leading)
            }
            Spacer(minLength: OmiSpacing.sm)
            Image(systemName: "arrow.up.right")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .accessibilityHidden(true)
          }
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(fact.kind.label): \(fact.text). Open cited transcript")
        .accessibilityIdentifier("meeting-brief-source-\(fact.kind.label)")
      }
    }
    .padding(OmiSpacing.lg)
    .glassCard(cornerRadius: PageGlass.rowRadius)
    .accessibilityIdentifier("meeting-memory-brief")
  }
}
