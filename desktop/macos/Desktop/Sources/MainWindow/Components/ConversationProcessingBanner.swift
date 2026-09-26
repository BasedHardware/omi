import OmiTheme
import SwiftUI

/// Banner above a conversation's details while its summary is still being
/// written. Wording follows the same clock as the list row's pill, and a
/// stalled pipeline gets its exit here too. A deferred (free-tier) row is
/// not on a clock: opening it is what started the work.
struct ConversationProcessingBanner: View {
  let conversation: ServerConversation
  /// Adopts the reprocessed conversation in the presenting view.
  let onReprocessed: (ServerConversation) -> Void

  @State private var isReprocessing = false

  static func title(phase: ConversationProcessingPhase, deferred: Bool) -> String {
    if deferred { return "Summarizing now…" }
    switch phase {
    case .summarizing: return "Summarizing…"
    case .slow: return "Taking longer than usual"
    case .stalled: return "Processing looks stuck"
    }
  }

  static func detail(phase: ConversationProcessingPhase, deferred: Bool) -> String {
    if deferred { return "Opening this conversation started its title, summary and action items" }
    switch phase {
    case .summarizing: return "Title, summary and action items usually land within two minutes"
    case .slow: return "Long conversations and busy periods can take a few minutes. The transcript is below."
    case .stalled: return "It has been over ten minutes. Reprocess runs the title and summary again."
    }
  }

  var body: some View {
    TimelineView(.periodic(from: .now, by: 15)) { timeline in
      let phase = ConversationProcessingProgress.phase(for: conversation, now: timeline.date)
      let deferred = conversation.deferred
      let offersReprocess = phase == .stalled && !deferred
      HStack(spacing: OmiSpacing.md) {
        if offersReprocess {
          Image(systemName: "exclamationmark.triangle.fill")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.errorRed)
        } else {
          ProgressView()
            .controlSize(.small)
        }
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(Self.title(phase: phase, deferred: deferred))
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text(Self.detail(phase: phase, deferred: deferred))
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        Spacer()
        if offersReprocess {
          Button {
            Task { await reprocess() }
          } label: {
            Text(isReprocessing ? "Reprocessing…" : "Reprocess")
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(Ink.primary)
              .padding(.horizontal, OmiSpacing.md)
              .frame(height: 26)
              .glassChip()
          }
          .buttonStyle(.plain)
          .disabled(isReprocessing)
          .accessibilityIdentifier("conversation-detail-reprocess-stalled")
        }
      }
      .padding(OmiSpacing.lg)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(Ink.rowFillHover.opacity(0.5))
      .cornerRadius(OmiChrome.smallControlRadius)
    }
  }

  /// Default-app reprocess: the same call the row's inline button makes.
  private func reprocess() async {
    guard !isReprocessing else { return }
    isReprocessing = true
    defer { isReprocessing = false }
    AnalyticsManager.shared.conversationReprocessedDefault(conversationId: conversation.id)
    do {
      let updated = try await APIClient.shared.reprocessConversation(conversationId: conversation.id)
      AppState.current?.replaceConversation(updated)
      onReprocessed(updated)
    } catch {
      logError("Failed to reprocess stalled conversation", error: error)
    }
  }
}
