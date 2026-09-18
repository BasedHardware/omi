import Foundation

/// Where a still-processing conversation sits on the clock. The pipeline has
/// no honest denominator for a percentage, so the UI communicates the only
/// thing it can observe: how long the wait has already lasted.
enum ConversationProcessingPhase: Equatable {
  /// Within the expected window — the backend is writing the title and summary.
  case summarizing
  /// Past the expected window. Still plausibly running; no action offered yet.
  case slow
  /// Long enough that a live processor is unlikely. Offer Reprocess inline.
  case stalled
}

/// Pure, clock-injected rules for the processing row. Thresholds are a
/// starting point; `Conversation Processing Completed` telemetry records the
/// measured elapsed time so they can be re-set from a real p95.
enum ConversationProcessingProgress {
  /// After this the pill stops promising "shortly".
  static let slowAfter: TimeInterval = 120
  /// After this the row offers Reprocess. Matches the backend's stale-orphan
  /// floor (300s lease) with headroom for a slow but live LLM call.
  static let stalledAfter: TimeInterval = 600
  /// How long after status flips to completed the backend's derived effects
  /// (memories, action items, embeddings) are typically still landing.
  static let derivedSettleGrace: TimeInterval = 45

  /// Processing starts when the recording ends, not when the row was created —
  /// a 40-minute meeting created 40 minutes ago is not 40 minutes stalled.
  static func processingStart(for conversation: ServerConversation) -> Date {
    conversation.finishedAt ?? conversation.createdAt
  }

  static func elapsed(for conversation: ServerConversation, now: Date) -> TimeInterval {
    max(0, now.timeIntervalSince(processingStart(for: conversation)))
  }

  static func phase(elapsed: TimeInterval) -> ConversationProcessingPhase {
    if elapsed >= stalledAfter { return .stalled }
    if elapsed >= slowAfter { return .slow }
    return .summarizing
  }

  static func phase(for conversation: ServerConversation, now: Date = Date()) -> ConversationProcessingPhase {
    phase(elapsed: elapsed(for: conversation, now: now))
  }

  /// Minimum words for a segment to be worth quoting as an identity.
  static let provisionalTitleMinimumWords = 5
  /// Character budget for a provisional title so it fits a single row line.
  static let provisionalTitleMaxLength = 64

  /// A row identity derived from the captured transcript so a processing
  /// conversation is never introduced to the user as "Processing…". Takes the
  /// first substantive segment, trims it to one line at a word boundary, and
  /// capitalises the first letter. Returns nil when no segment is substantive.
  static func provisionalTitle(from segments: [TranscriptSegment]) -> String? {
    for segment in segments {
      let words = segment.text.split(whereSeparator: { $0.isWhitespace })
      guard words.count >= provisionalTitleMinimumWords else { continue }
      var kept: [Substring] = []
      var length = 0
      for word in words {
        let next = length + word.count + (kept.isEmpty ? 0 : 1)
        if next > provisionalTitleMaxLength { break }
        kept.append(word)
        length = next
      }
      // A title budget that cannot fit the minimum words is not a title.
      guard kept.count >= provisionalTitleMinimumWords else { continue }
      var text = kept.joined(separator: " ")
      if kept.count < words.count {
        text = text.trimmingCharacters(in: CharacterSet(charactersIn: ".,;:!?-–—")) + "…"
      }
      return text.prefix(1).uppercased() + text.dropFirst()
    }
    return nil
  }
}
