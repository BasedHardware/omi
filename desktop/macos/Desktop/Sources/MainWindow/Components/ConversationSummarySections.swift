//
//  ConversationSummarySections.swift — the headed blocks selected as a summary body.
//
//  `ConversationSummarySelection` decides whether these blocks are the canonical body. This view
//  must stay a single projection: callers never mount it alongside the compatibility overview.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// The one summary body mounted by conversation detail.
///
/// Keeping the selection branch here makes the no-duplicate invariant testable against the actual
/// production composition. The parent detail view owns the surrounding header/actions and only
/// supplies the transcript navigation callback.
struct ConversationSummaryBody: View {
  let conversation: ServerConversation
  let onOpenSources: (([String]) -> Void)?

  private var selection: ConversationSummarySelection.Primary {
    ConversationSummarySelection.primarySummary(for: conversation)
  }

  private var attribution: ConversationSummaryProvenanceState.Attribution? {
    ConversationSummaryProvenanceState.attribution(
      localSummaryRuntime: conversation.localSummary?.runtime,
      hasSummaryBody: selection.kind != .empty
    )
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      // `.empty` previously fell through to the markdown branch and rendered an
      // empty string: a title followed by blank space, with nothing said about
      // whether a summary had failed, was still coming, or would never arrive.
      if selection.kind == .empty {
        ConversationSummaryEmptyStateView(
          state: ConversationSummaryProvenanceState.empty(
            deferred: conversation.deferred,
            localSummaryRuntime: conversation.localSummary?.runtime,
            isProcessing: conversation.status == .processing
          )
        )
        .padding(.horizontal, OmiSpacing.lg)
      } else if selection.kind == .sections {
        ConversationSummarySections(
          sections: conversation.structured.sections,
          transcriptSegments: conversation.transcriptSegments,
          onOpenSources: onOpenSources
        )
        .padding(.horizontal, OmiSpacing.lg)
      } else {
        OmiMarkdown(
          text: selection.content,
          sender: .ai,
          appKitProseSelection: true,
          documentProse: true
        )
        .frame(maxWidth: .infinity, alignment: .leading)
      }

      if let attribution, attribution.isWorthDisplaying {
        ConversationSummaryAttributionBadge(attribution: attribution)
          .padding(.horizontal, OmiSpacing.lg)
      }
    }
  }
}

/// Where this particular summary was produced.
///
/// Per conversation, never per tier: free mobile conversations are summarized in
/// the cloud today (`free_tier_processing_policy` returns `process_normally` for
/// every non-desktop source), so a tier-wide "processed on your device" claim on
/// this surface would be false for the same account on another platform.
struct ConversationSummaryAttributionBadge: View {
  let attribution: ConversationSummaryProvenanceState.Attribution

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: attribution.systemImage)
        .imageScale(.small)
      Text(attribution.label)
    }
    .font(.caption)
    .foregroundColor(Ink.tertiary)
    .accessibilityElement(children: .combine)
    .accessibilityLabel(attribution.label)
  }
}

/// Shown instead of an empty summary body.
///
/// The transcript is mentioned in every message because it is the thing the
/// reader still has, and on this surface it is immediately below.
struct ConversationSummaryEmptyStateView: View {
  let state: ConversationSummaryProvenanceState.Empty

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      Text(state.title)
        .font(.subheadline.weight(.medium))
        .foregroundColor(Ink.secondary)
      Text(state.message)
        .font(.callout)
        .foregroundColor(Ink.tertiary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .accessibilityElement(children: .combine)
    .accessibilityLabel("\(state.title). \(state.message)")
  }
}

/// The conversation's headed summary blocks, in backend order.
///
/// This is used only when `ConversationSummarySelection` has selected the sections projection, so
/// it must never be mounted in addition to the selected overview/app body. Source ids are filtered
/// against the loaded transcript before an affordance is shown; stale or unknown ids remain hidden.
struct ConversationSummarySections: View {
  let sections: [SummarySection]
  let transcriptSegments: [TranscriptSegment]
  let onOpenSources: (([String]) -> Void)?

  init(
    sections: [SummarySection],
    transcriptSegments: [TranscriptSegment] = [],
    onOpenSources: (([String]) -> Void)? = nil
  ) {
    self.sections = sections
    self.transcriptSegments = transcriptSegments
    self.onOpenSources = onOpenSources
  }

  private var visibleSections: [SummarySection] {
    sections.filter { !$0.bodyMarkdown.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
  }

  var body: some View {
    if !visibleSections.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        // Keyed by position, not by heading. These blocks are model-written, so two can share a
        // heading — or have none at all, which this view explicitly allows below — and identical
        // `ForEach` ids make SwiftUI drop or duplicate rows rather than render both.
        ForEach(Array(visibleSections.enumerated()), id: \.offset) { _, section in
          VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            // Markdown, not `Text`: these bodies carry lists and emphasis, and a plain `Text`
            // renders their syntax as literal characters. Selection is AppKit prose — the same
            // contract as chat — because a SwiftUI native-selection modifier on an ancestor of
            // `OmiMarkdown` installs SelectionOverlay around a tall attributed block and
            // re-lays it out while the reader scrolls (FC-selection-overlay-layout-loop).
            OmiMarkdown(
              text: ConversationSummarySelection.renderSections([section]),
              style: .assistant,
              appKitProseSelection: true,
              documentProse: true
            )

            let sourceIDs = ConversationSummarySelection.resolvableSourceIDs(
              section.sourceSegmentIDs, segments: transcriptSegments)
            if !sourceIDs.isEmpty, let onOpenSources {
              Button {
                onOpenSources(sourceIDs)
              } label: {
                Label(
                  sourceIDs.count == 1 ? "Source" : "Sources (\(sourceIDs.count))",
                  systemImage: "text.quote"
                )
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
              }
              .buttonStyle(.plain)
              .accessibilityIdentifier("conversation-summary-section-sources")
              .help("Open the supporting transcript")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
        }
      }
      .accessibilityIdentifier("conversation-summary-sections")
    }
  }
}
