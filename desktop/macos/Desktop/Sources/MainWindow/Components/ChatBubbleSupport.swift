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

/// Assistant `text_delta` before the first tool call is commentary, not the answer.
/// The host still concatenates every delta into `message.text`; this projection is
/// what the bubble, copy affordance, and truncation must use instead.
enum ChatAssistantAnswerText {
  static func visible(
    contentBlocks: [ChatContentBlock],
    fallback: String,
    isStreaming: Bool
  ) -> String {
    func texts(in slice: ArraySlice<ChatContentBlock>) -> [String] {
      slice.compactMap { block in
        guard case .text(_, let text) = block else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
      }
    }

    let fallbackText = fallback.trimmingCharacters(in: .whitespacesAndNewlines)
    guard
      let lastTool = contentBlocks.lastIndex(where: { block in
        if case .toolCall = block { return true }
        return false
      })
    else {
      let fromBlocks = texts(in: contentBlocks[...]).joined(separator: "\n")
      return fromBlocks.isEmpty ? fallbackText : fromBlocks
    }

    let afterTools = texts(in: contentBlocks[(lastTool + 1)...])
    if !afterTools.isEmpty {
      return afterTools.joined(separator: "\n")
    }
    if isStreaming {
      return ""
    }
    let beforeTools = texts(in: contentBlocks[..<lastTool])
    if !beforeTools.isEmpty {
      return beforeTools.joined(separator: "\n")
    }
    return fallbackText
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
  /// - Parameters:
  ///   - calendar: decides *and* renders. Which day a message belongs to and which day the stamp
  ///     says have to be the same question: `Date.FormatStyle` otherwise resolves against
  ///     `.autoupdatingCurrent`, so a caller passing any other calendar would get "today" decided in
  ///     one zone and the clock time printed in another — a 1:28 PM stamp on a row the same call
  ///     just decided was yesterday.
  ///   - locale: how the stamp is worded; the user's, so the month reads in their language.
  static func text(
    for date: Date, now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current
  ) -> String {
    func render(_ style: Date.FormatStyle) -> String {
      var style = style
      style.calendar = calendar
      style.timeZone = calendar.timeZone
      style.locale = locale
      return date.formatted(style)
    }

    let time = render(.dateTime.hour().minute())
    if calendar.isDate(date, inSameDayAs: now) { return time }
    if calendar.component(.year, from: date) == calendar.component(.year, from: now) {
      return "\(render(.dateTime.month(.abbreviated).day())) · \(time)"
    }
    return "\(render(.dateTime.year().month(.abbreviated).day())) · \(time)"
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

/// **The message body's ground, decided as arithmetic before it is drawn.**
///
/// The fill, the corner that rounds it and the padding that holds text away from that corner are one
/// decision, and this is the only place that makes it. Splitting them is what broke the transcript:
/// the spacing rebuild correctly took the capsule's padding off the assistant's reply — an unfilled
/// reply is not a container and must not be indented like one — and left the capsule's *clip* behind.
///
/// A rounded clip is not a decoration on the corners; it is a curve that withdraws from the leading
/// edge for the whole first `radius` points of the box. At `PageGlass.cardRadius` on a three-line
/// reply that is 9 pt of withdrawal where the first line's cap height sits, tapering to nothing by its
/// baseline. With no padding to absorb it, every reply lost the top-left of its opening glyph and the
/// bottom-left of its closing line's — `I` became a low stub, `l` a high one — while the lines in
/// between, at the box's full width, were untouched. That taper is the signature: a defect that reads
/// as "the first character is missing" but only on a block's first and last line.
enum ChatMessageBlockGeometry {
  /// Only a container is padded like one.
  static func horizontalPadding(filled: Bool) -> CGFloat { filled ? OmiSpacing.md : 0 }
  static func verticalPadding(filled: Bool) -> CGFloat { filled ? OmiSpacing.sm : 0 }

  /// Whether the block paints a ground of its own. An assistant reply's ground is the glass panel it
  /// sits on, so it paints nothing — and therefore has no shape, nothing to round, and nothing that
  /// could clip its own text.
  static func drawsGround(filled: Bool) -> Bool { filled }

  /// The corner of that ground. Zero when there is no ground: a shape that is never drawn must never
  /// be reintroduced as a clip either.
  static func cornerRadius(filled: Bool) -> CGFloat { filled ? PageGlass.cardRadius : 0 }
}

extension View {
  /// The message body's ground. See `ChatMessageBlockGeometry` for why the fill is a background shape
  /// rather than a clip: a block only ever rounds what it painted, never the text handed to it.
  func chatMessageBlock(filled: Bool) -> some View {
    padding(.horizontal, ChatMessageBlockGeometry.horizontalPadding(filled: filled))
      .padding(.vertical, ChatMessageBlockGeometry.verticalPadding(filled: filled))
      .background {
        if ChatMessageBlockGeometry.drawsGround(filled: filled) {
          RoundedRectangle(
            cornerRadius: ChatMessageBlockGeometry.cornerRadius(filled: filled),
            style: .continuous
          )
          .fill(Ink.rowFillHover)
        }
      }
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
  let kind: ProactiveNotificationKind

  private var badge: ProactiveNotificationBadge {
    ProactiveNotificationBadge(kind: kind)
  }

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Image(systemName: badge.systemImage)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        // Neutral, not accent: a notification badge is ambient history, not the one
        // actionable element `Ink.accent` is reserved for (see Ink.swift). Blue here made
        // every past notification shout for attention it does not want.
        .foregroundColor(Ink.secondary)
        .frame(width: 24, height: 24)
        .background(Ink.rowFill, in: Circle())
        .accessibilityHidden(true)
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(badge.label)
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundColor(Ink.secondary)
        OmiMarkdown(text: text, sender: .ai)
      }
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
    .accessibilityLabel("\(badge.label): \(text)")
  }
}

struct ProactiveNotificationBadge: Equatable {
  let label: String
  let systemImage: String

  /// Shared glyph contract: Insight uses `sparkles` everywhere; Suggestion keeps `lightbulb`.
  static let insightSystemImage = "sparkles"
  static let suggestionSystemImage = "lightbulb"

  init(kind: ProactiveNotificationKind) {
    switch kind {
    case .suggestion:
      (label, systemImage) = ("Suggestion", Self.suggestionSystemImage)
    case .insight:
      (label, systemImage) = ("Insight", Self.insightSystemImage)
    case .task:
      (label, systemImage) = ("Task", "checkmark.circle")
    case .memory:
      (label, systemImage) = ("Memory", "brain.head.profile")
    case .goal:
      (label, systemImage) = ("Goal", "target")
    case .meetingNotes:
      (label, systemImage) = ("Meeting notes", "text.document")
    case .resurface:
      (label, systemImage) = ("Resurfaced", "clock.arrow.circlepath")
    case .general:
      (label, systemImage) = ("Notification", "bell")
    }
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

/// Footer actions for an assistant row. A finished reply is rateable as soon as
/// it has copyable text; waiting for `isSynced` hid thumbs on the live tail
/// because completion clears streaming before the journal remote id lands.
/// Persistence of that rating is `ChatMessageRatingPersistence` — show the
/// buttons now, PATCH after sync.
enum ChatBubbleMetadataBand: Equatable {
  case hidden
  case timestampOnly
  case actions

  static func of(_ message: ChatMessage) -> Self {
    guard message.sender == .ai, !message.isStreaming else { return .hidden }
    guard !message.copyableText.isEmpty else { return .timestampOnly }
    return .actions
  }
}

/// Visible identity for `ChatBubble`'s Equatable skip. Sync, metadata, and
/// structured blocks change the footer and tool rail without changing `text`.
enum ChatBubbleIdentity {
  static func equal(
    _ lhs: ChatMessage,
    _ rhs: ChatMessage,
    appIDs: (String?, String?),
    showsOmiMark: (Bool, Bool),
    isDuplicate: (Bool, Bool)
  ) -> Bool {
    guard !lhs.isStreaming && !rhs.isStreaming else { return false }
    return lhs.id == rhs.id
      && lhs.text == rhs.text
      && lhs.rating == rhs.rating
      && lhs.isSynced == rhs.isSynced
      && lhs.copyableText == rhs.copyableText
      && lhs.displayResources == rhs.displayResources
      && lhs.journalStatus == rhs.journalStatus
      && lhs.citations.map(\.id) == rhs.citations.map(\.id)
      && (lhs.metadata != nil) == (rhs.metadata != nil)
      && ChatContentBlockCodec.comparisonData(lhs.contentBlocks)
        == ChatContentBlockCodec.comparisonData(rhs.contentBlocks)
      && appIDs.0 == appIDs.1
      && showsOmiMark.0 == showsOmiMark.1
      && isDuplicate.0 == isDuplicate.1
  }
}
