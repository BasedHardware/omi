//
//  ConversationSummarySections.swift — the headed blocks a summary is actually made of.
//
//  The backend stopped putting the substance of a summary in `overview`. `overview` is now a short
//  compatibility paragraph and the real writing — what was discussed, the friction, the follow-ups —
//  arrives as `structured.sections`: a list of headings, each with a markdown body. The desktop's
//  domain model dropped the field entirely, so both detail surfaces were rendering the compatibility
//  paragraph and presenting it as the whole summary. That is the "the summary used to be better"
//  regression: the writing did not get worse, the client stopped reading most of it.
//
//  This is one view rather than two because the two surfaces that show a summary — the legacy
//  `ConversationDetailView` and the chat-first `CaptureArchivePage` — already drifted once (one
//  renders markdown, the other rendered plain `Text`). A shared renderer is what keeps the next
//  section the backend adds from appearing on only one of them.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// The conversation's headed summary blocks, in backend order.
///
/// Renders nothing when a capture predates the notes pipeline — those carry an empty `sections`
/// and their whole summary really is `overview`, which the caller renders above this.
struct ConversationSummarySections: View {
  let sections: [SummarySection]

  var body: some View {
    if !sections.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        // Keyed by position, not by heading. These blocks are model-written, so two can share a
        // heading — or have none at all, which this view explicitly allows below — and identical
        // `ForEach` ids make SwiftUI drop or duplicate rows rather than render both.
        ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            if !section.heading.isEmpty {
              Text(section.heading)
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(Ink.primary)
                .textSelection(.enabled)
            }
            // Markdown, not `Text`: these bodies carry lists and emphasis, and a plain `Text`
            // renders their syntax as literal characters.
            OmiMarkdown(text: section.bodyMarkdown, style: .assistant)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
        }
      }
      .accessibilityIdentifier("conversation-summary-sections")
    }
  }
}
