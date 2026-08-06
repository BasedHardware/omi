import Foundation
import OmiTheme
import SwiftUI

/// Pure collapsed-body policy so the transcript's truncation contract can be
/// covered without requiring a running SwiftUI window.
enum ChatBubbleTruncation {
  static let threshold = 500

  static func shouldTruncate(text: String, isStreaming: Bool, isExpanded: Bool) -> Bool {
    !isStreaming && text.count > threshold && !isExpanded
  }

  static func displayText(_ text: String, isStreaming: Bool, isExpanded: Bool) -> String {
    guard shouldTruncate(text: text, isStreaming: isStreaming, isExpanded: isExpanded) else {
      return text
    }
    return String(text.prefix(threshold)).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
  }
}

/// Shared understated date treatment for a transcript row and its prompt-rail
/// preview. Keeping this outside the bubble makes the time contextual rather
/// than part of the message itself.
struct ChatMessageTimestamp: View {
  let date: Date

  var body: some View {
    // Two rungs on glass, so the second rung straight. The old `.opacity(0.82)`
    // on top of `Ink.secondary` was a third rung by arithmetic, at the one point
    // size where it could least afford one.
    Text(ChatMessageTimestampFormat.text(for: date))
      .scaledFont(size: OmiType.micro)
      .foregroundColor(Ink.secondary)
      .monospacedDigit()
  }
}

/// The time a row arrived, at the length it is actually read at.
///
/// `Aug 6, 2026 at 1:28 PM` under every reply is a date stamp on a chat message:
/// six words of chrome for a fact wanted to the minute. Parked at the far end of
/// the row from the controls it shares a line with, it stopped reading as part of
/// the message and started reading as page furniture. Today says the time; this
/// year adds the day; only another year is worth naming.
enum ChatMessageTimestampFormat {
  static func text(for date: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
    let time = date.formatted(.dateTime.hour().minute())
    if calendar.isDate(date, inSameDayAs: now) { return time }
    if calendar.component(.year, from: date) == calendar.component(.year, from: now) {
      return "\(date.formatted(.dateTime.month(.abbreviated).day())) · \(time)"
    }
    return "\(date.formatted(.dateTime.year().month(.abbreviated).day())) · \(time)"
  }
}

/// What a transcript row *is*, decided once from the message instead of
/// re-derived by whichever modifier happens to be reading `sender`.
///
/// Three cases because the surface has three jobs: words you typed, an answer to
/// them, and something omi said with nothing in front of it. The first two are a
/// conversation. The third has to account for its own presence.
enum ChatRowPresentation: Equatable {
  /// Your own words — a filled capsule on the trailing edge.
  case userTurn
  /// omi answering you. Deliberately unfilled; see `chatMessageBlock(filled:)`.
  case assistantReply
  /// omi speaking first. Journaled under
  /// `ChatContinuityInvariants.proactiveNotificationContinuityKeyPrefix` (INV-6).
  case proactivePush

  static func of(_ message: ChatMessage) -> Self {
    guard message.sender != .user else { return .userTurn }
    return ChatContinuityInvariants.isProactiveNotification(message)
      ? .proactivePush : .assistantReply
  }

  /// Only a user turn is a container, so only a user turn is padded like one.
  var isFilled: Bool { self == .userTurn }
}

extension View {
  /// The message body's ground.
  ///
  /// A user turn is a filled capsule and the padding is what makes it one. An
  /// assistant reply has no fill — on a glass panel the glass is the ground, and
  /// a second fill inside it would be a box inside a box — but the reply was
  /// still wearing the capsule's padding: 12 pt of phantom indent and 16 pt of
  /// dead vertical air wrapped around bare text with nothing to wrap it in. That
  /// is what put two one-line replies further apart than a paragraph break.
  /// Padding belongs to the container, so it now goes where the container goes.
  func chatMessageBlock(filled: Bool) -> some View {
    padding(.horizontal, filled ? OmiSpacing.md : 0)
      .padding(.vertical, filled ? OmiSpacing.sm : 0)
      .background(filled ? Ink.rowFillHover : Color.clear)
      .clipShape(RoundedRectangle(cornerRadius: PageGlass.cardRadius, style: .continuous))
  }
}

/// A proactive push, drawn as the thing it is rather than as a reply.
///
/// Nothing above it explains why it is there, so it says so itself: a bell on the
/// leading edge and a quiet fill that lifts it off the panel. Left bare it
/// rendered as a one-line string dropped into the middle of a conversation —
/// visually identical to an answer, but to a question nobody asked. The fill is
/// not a contradiction of the bare-assistant rule above: a reply is unfilled
/// *because* the question above it is its context, and this row has none.
struct ChatProactivePushRow: View {
  let text: String

  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
      Image(systemName: "bell")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.secondary)
      OmiMarkdown(text: text, sender: .ai)
      Spacer(minLength: 0)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .stroke(Ink.glassEdge, lineWidth: 1)
    )
    .accessibilityElement(children: .combine)
    .accessibilityLabel("Omi noticed: \(text)")
  }
}

/// Visibility rule for the quiet timeline's per-message metadata row
/// (rating / copy / info / timestamp). Keyboard parity is part of the
/// contract: focus on any metadata control must reveal the row, otherwise
/// Tab / Full Keyboard Access ends up on an invisible button.
enum ChatBubbleMetadataReveal {
  static func isVisible(hovering: Bool, controlFocused: Bool, transientFeedback: Bool) -> Bool {
    hovering || controlFocused || transientFeedback
  }
}

struct BackgroundAgentSummary: Equatable {
  let agentID: UUID?
  let prompt: String
  let output: String

  static func parse(_ text: String) -> BackgroundAgentSummary? {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("[Background agent") else { return nil }
    guard let close = trimmed.firstIndex(of: "]") else { return nil }

    let headerStart = trimmed.index(trimmed.startIndex, offsetBy: 1)
    let header = String(trimmed[headerStart..<close])
    guard header.hasPrefix("Background agent") else { return nil }

    var remainder = String(header.dropFirst("Background agent".count))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    var agentID: UUID?

    if remainder.hasPrefix("id=") {
      remainder.removeFirst(3)
      let idEnd = remainder.firstIndex { $0 == " " || $0 == "—" } ?? remainder.endIndex
      let idText = String(remainder[..<idEnd]).trimmingCharacters(in: .whitespacesAndNewlines)
      agentID = UUID(uuidString: idText)
      remainder = String(remainder[idEnd...]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    if remainder.hasPrefix("—") {
      remainder.removeFirst()
      remainder = remainder.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    let outputStart = trimmed.index(after: close)
    let output = String(trimmed[outputStart...]).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !output.isEmpty else { return nil }

    return BackgroundAgentSummary(
      agentID: agentID,
      prompt: remainder.isEmpty ? "Background agent" : remainder,
      output: output
    )
  }
}
