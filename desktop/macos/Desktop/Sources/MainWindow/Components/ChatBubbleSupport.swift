import Foundation
import OmiTheme
import SwiftUI

/// Pure collapsed-body policy so the transcript's truncation contract can be
/// covered without requiring a running SwiftUI window.
///
/// The budget is measured in viewports of rendered text, not characters. Five
/// hundred characters was five lines: every real answer collapsed, and the
/// reader clicked "Show more" under nearly everything they asked. A reply may
/// now fill `viewportHeightsBeforeCollapse` screens before the transcript
/// offers to fold it, and a reply that long starts folded — restored history
/// should not be mostly one old answer.
enum ChatBubbleTruncation {
  /// How many screens of prose a reply may take before it is offered collapsed.
  static let viewportHeightsBeforeCollapse: CGFloat = 2
  /// Stands in until the transcript has measured itself, and in tests.
  static let fallbackViewportHeight: CGFloat = 720
  static let fallbackColumnWidth: CGFloat = 640
  /// A collapsed body is never shorter than this many lines, whatever the
  /// window: a few lines and "Show more" is a teaser, not a message.
  static let minimumLines = 12

  /// What the collapsed body may hold, derived from the transcript's geometry.
  struct Budget: Equatable {
    /// Rendered lines the collapsed body may take.
    let lines: Int
    /// Characters one full line of prose holds at this width.
    let charactersPerLine: Int

    static let fallback = ChatBubbleTruncation.budget(
      viewportHeight: fallbackViewportHeight, columnWidth: fallbackColumnWidth)
  }

  /// - Parameters:
  ///   - viewportHeight: the transcript's visible height; `0` before it is measured.
  ///   - columnWidth: the message column; `0` before it is measured.
  ///   - fontScale: the reader's text-size preference, as the prose renders it.
  static func budget(viewportHeight: CGFloat, columnWidth: CGFloat, fontScale: CGFloat = 1) -> Budget {
    let fontSize = round(14 * max(fontScale, 0.5))
    let lineHeight = fontSize * 1.25 + OmiMarkdownContent.chatLineSpacing(fontSize: fontSize)
    let height = viewportHeight > 0 ? viewportHeight : fallbackViewportHeight
    let width = columnWidth > 0 ? columnWidth : fallbackColumnWidth
    // SF at text sizes averages about half an em per glyph, and prose wraps
    // before the edge, so a line holds a bit less than the width allows.
    let charactersPerLine = max(20, Int((width / (fontSize * 0.5)) * 0.85))
    let lines = max(minimumLines, Int((height * viewportHeightsBeforeCollapse) / lineHeight))
    return Budget(lines: lines, charactersPerLine: charactersPerLine)
  }

  /// Lines the text takes when wrapped at `charactersPerLine`: each source line
  /// wraps on its own, and a blank one is the small gap between paragraphs.
  static func estimatedLines(_ text: String, charactersPerLine: Int) -> Double {
    text.split(separator: "\n", omittingEmptySubsequences: false).reduce(0) { total, line in
      total + lineCost(line, charactersPerLine: charactersPerLine)
    }
  }

  private static func lineCost(_ line: Substring, charactersPerLine: Int) -> Double {
    let count = line.trimmingCharacters(in: .whitespaces).count
    guard count > 0 else { return 0.35 }
    return max(1, (Double(count) / Double(max(charactersPerLine, 1))).rounded(.up))
  }

  static func exceedsBudget(_ text: String, budget: Budget) -> Bool {
    estimatedLines(text, charactersPerLine: budget.charactersPerLine) > Double(budget.lines)
  }

  /// Whether an answer that has just finished streaming keeps its full body.
  ///
  /// Truncation is for restored history — a long transcript should not be
  /// mostly one old reply. An answer the reader just watched arrive is the
  /// opposite case: clamping it at the moment it settles takes back everything
  /// they read, and shrinks the document by thousands of points under a
  /// transcript that was following the live edge, so the reply they were
  /// reading is replaced by its own first paragraph. A forty-item list
  /// collapsed to three the instant it finished.
  static func settlingKeepsFullBody(wasStreaming: Bool?, isStreaming: Bool?) -> Bool {
    wasStreaming == true && isStreaming != true
  }

  static func shouldTruncate(
    text: String, isStreaming: Bool, isExpanded: Bool, budget: Budget = .fallback
  ) -> Bool {
    !isStreaming && !isExpanded && exceedsBudget(text, budget: budget)
  }

  static func displayText(
    _ text: String, isStreaming: Bool, isExpanded: Bool, budget: Budget = .fallback
  ) -> String {
    guard shouldTruncate(text: text, isStreaming: isStreaming, isExpanded: isExpanded, budget: budget)
    else { return text }
    return collapsedPrefix(text, budget: budget) + "…"
  }

  /// The first `budget.lines` rendered lines, cut at a source line where it can
  /// be — mid-word cuts read as damage — and by characters only inside a single
  /// paragraph too long to fit. A fence opened inside the kept prefix is closed
  /// so the hidden remainder does not turn the ellipsis into code.
  static func collapsedPrefix(_ text: String, budget: Budget) -> String {
    var remaining = Double(budget.lines)
    var kept = [Substring]()
    var fenceOpen = false
    for line in text.split(separator: "\n", omittingEmptySubsequences: false) {
      let cost = lineCost(line, charactersPerLine: budget.charactersPerLine)
      if cost > remaining {
        let characters = Int(remaining.rounded(.down)) * budget.charactersPerLine
        if characters > 0 { kept.append(line.prefix(characters)) }
        break
      }
      remaining -= cost
      if line.trimmingCharacters(in: .whitespaces).hasPrefix("```") { fenceOpen.toggle() }
      kept.append(line)
    }
    var prefix = kept.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    if fenceOpen { prefix += "\n```\n" }
    return prefix
  }
}

// MARK: - Transcript viewport

private struct ChatTranscriptViewportKey: EnvironmentKey {
  static let defaultValue: CGSize = .zero
}

extension EnvironmentValues {
  /// The visible size of the transcript a row is drawn in, so a row can size
  /// its own collapse budget in screens. `.zero` until the transcript measures.
  var chatTranscriptViewport: CGSize {
    get { self[ChatTranscriptViewportKey.self] }
    set { self[ChatTranscriptViewportKey.self] = newValue }
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

    // A body that is only the blocks' own degradation has nothing the cards
    // above it do not already say, so it is not answer text at all.
    let fallbackText =
      ChatStructuredFallbackText.bodyIsBlockProjection(text: fallback, contentBlocks: contentBlocks)
      ? "" : fallback.trimmingCharacters(in: .whitespacesAndNewlines)
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

/// The unaware-client projection of a turn's structured blocks.
///
/// A turn that answers with cards writes no prose, so the runtime synthesizes
/// one line per block — "Goal - Make Omi Great Again", the bare word "Task"
/// once per task card — and puts it on the message's ordinary text field. That
/// is the degradation contract for clients that cannot draw the cards
/// (`agent/src/runtime/content-block-fallback.ts`). A client that *does* draw
/// them must recognize its own projection and not print it back underneath the
/// controls it just rendered. Mobile recognizes it the same way, in
/// `ServerMessage.textIsStructuredFallback`; the two must agree, so this
/// mirrors the producer case for case.
enum ChatStructuredFallbackText {
  static func bodyIsBlockProjection(text: String, contentBlocks: [ChatContentBlock]) -> Bool {
    guard !contentBlocks.isEmpty else { return false }
    let projection = projected(contentBlocks)
    guard !projection.isEmpty else { return false }
    let body = text.trimmingCharacters(in: .whitespacesAndNewlines)
    return body.isEmpty || normalized(body) == normalized(projection)
  }

  static func projected(_ contentBlocks: [ChatContentBlock]) -> String {
    contentBlocks.map(line(for:)).filter { !$0.isEmpty }.joined(separator: "\n")
  }

  private static func normalized(_ value: String) -> String {
    value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
  }

  private static func labelled(_ label: String, _ details: String?...) -> String {
    var unique: [String] = []
    for detail in details {
      let trimmed = detail?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      guard !trimmed.isEmpty, !unique.contains(trimmed) else { continue }
      unique.append(trimmed)
    }
    return unique.isEmpty ? label : "\(label) - \(unique.joined(separator: " - "))"
  }

  private static func nonEmpty(_ value: String, or fallback: String) -> String {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? fallback : trimmed
  }

  private static func line(for block: ChatContentBlock) -> String {
    switch block {
    case .text(_, let text):
      return nonEmpty(text, or: "Message")
    case .toolCall(_, let name, _, _, let input, let output):
      return labelled("Tool", name, output ?? input?.summary)
    case .thinking(_, let text):
      return labelled("Thinking", text)
    case .discoveryCard(_, let title, let summary, _):
      return labelled("Discovery", title, summary)
    case .questionCard(_, _, let text, _, _, _, _):
      return nonEmpty(text, or: "Question")
    case .taskCard:
      return "Task"
    case .goalLink(_, _, let summary):
      return labelled("Goal", summary)
    case .captureLink(_, _, _, let summary):
      return labelled("Capture", summary)
    case .conversationLink(_, _, let summary, _):
      return labelled("Meeting notes ready", summary)
    case .memoryLink(_, _, let summary):
      return labelled("Memory", summary)
    case .citation(_, let reference):
      return labelled("Source", reference.title, reference.preview)
    case .agentSpawn(_, _, _, _, let title, let objective, _):
      return labelled("Agent started", title, objective)
    case .agentCompletion(_, _, _, _, let title, _, let output, _):
      return labelled("Agent completed", title, output)
    case .memoryReviewCard:
      return "Memory review"
    case .followUp(_, let question):
      return nonEmpty(question, or: "Follow-up")
    }
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

  /// Category chrome already lives on the badge; do not also draw it as the body.
  private var displayText: String {
    FloatingControlBarManager.chatDisplayText(text, kind: kind)
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
        if !displayText.isEmpty {
          OmiMarkdown(text: displayText, sender: .ai)
        }
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
    .accessibilityLabel(
      displayText.isEmpty ? badge.label : "\(badge.label): \(displayText)")
  }
}

struct ProactiveNotificationBadge: Equatable {
  let label: String
  let systemImage: String

  /// Shared glyph contract: Insight uses `sparkles` everywhere; Focus keeps `lightbulb`.
  static let insightSystemImage = "sparkles"
  static let suggestionSystemImage = "lightbulb"

  /// The user-facing taxonomy is exactly five proactive categories — Focus, Task,
  /// Insight, Memory, Integration — matching the five toggles in Settings →
  /// Notifications. Internal kinds stay distinct (their raw values are persisted in
  /// chat continuity keys), but every one of them presents as one of the five: Focus
  /// is the focus-nudge assistant alone; generic tips, resurfaced items, and generated
  /// goals are all insights; meeting action items are tasks; connect-an-app offers are
  /// integrations. `.general` is reserved for functional system alerts, which sit
  /// outside the proactive taxonomy.
  init(kind: ProactiveNotificationKind) {
    switch kind {
    case .suggestion:
      (label, systemImage) = ("Focus", Self.suggestionSystemImage)
    case .insight, .resurface, .goal:
      (label, systemImage) = ("Insight", Self.insightSystemImage)
    case .task, .meetingNotes:
      (label, systemImage) = ("Task", "checkmark.circle")
    case .memory:
      (label, systemImage) = ("Memory", "brain.head.profile")
    case .integration:
      (label, systemImage) = ("Integration", "sparkles.rectangle.stack")
    case .functional:
      (label, systemImage) = ("Omi", "bell")
    case .general:
      // Decode-only: rows journaled before proactive kinds were part of the
      // continuity key. No producer can reach it (`showNotification` requires a
      // kind), so this arm is history, not a category.
      (label, systemImage) = ("Notification", "bell")
    case .trial, .onboarding:
      // Never journaled, so never rendered as a transcript row. Kept exhaustive
      // so a future decision to journal them has to state its badge here.
      (label, systemImage) = ("Omi", "bell")
    case .dailyRecap:
      // Never journaled either — the recap's transcript presence is the
      // dedicated `ChatDailyRecapRow` day boundary, not a bell card. Kept
      // exhaustive for the same reason.
      (label, systemImage) = ("Daily Recap", "calendar")
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
    guard !message.copyableText.isEmpty else {
      // **A row whose whole content is a rich block gets no band.** A memory
      // card carries its own header and time on its face; reserving a strip
      // for a second timestamp underneath it left the card floating in dead
      // space with nothing to copy or rate. A row with nothing at all still
      // keeps its timestamp — that stamp is all it has.
      return message.contentBlocks.isEmpty ? .timestampOnly : .hidden
    }
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
      // `copyableText` is deliberately absent: it derives purely from
      // `(contentBlocks, text, isStreaming)` — every one of which this
      // conjunction already compares — so its term was logically redundant.
      // It was also ruinous: SwiftUI re-runs this equality for every bubble on
      // every transcript body pass, and each evaluation re-derived and
      // whitespace-normalized the full answer text, dominating sampled switch
      // mounts (~600 ms of a ~1.3 s navigate-to-chat).
      && lhs.displayResources == rhs.displayResources
      && lhs.journalStatus == rhs.journalStatus
      && lhs.citations.map(\.id) == rhs.citations.map(\.id)
      && (lhs.metadata != nil) == (rhs.metadata != nil)
      // Direct field equality. This used to go through
      // `ChatContentBlockCodec.comparisonData`, which JSON-encoded BOTH sides of
      // every unchanged row — two serializations per bubble per transcript
      // pass — for a comparison the enum can make field-by-field for free.
      // It is deliberately slightly stricter than the old encode: toolCall
      // status pairs the encoder collapsed (.running/.slow/.stalled all
      // persisted as "running") now compare unequal, which only ever forces
      // an extra re-render mid-turn — the isStreaming guard above already
      // re-renders through those states anyway.
      && lhs.contentBlocks == rhs.contentBlocks
      && appIDs.0 == appIDs.1
      && showsOmiMark.0 == showsOmiMark.1
      && isDuplicate.0 == isDuplicate.1
  }
}

/// A task Omi proposed while listening, rendered in chat as a card the reader can
/// act on. INVARIANT I1: the proposal is a pending Candidate — it is not in the
/// task list, and "Add to Tasks" is the gesture that puts it there. This replaces
/// the old "✓ Saved to Tasks" receipt, which announced a write the user never asked
/// for.
///
/// Carried through the transcript inside the message text, the same way
/// `BackgroundAgentSummary` is, so it survives a reload with no schema change:
///   `[Suggested task id=<candidateID>] <description>`
struct SuggestedTaskChatCard: Equatable {
  let candidateID: String
  let description: String

  private static let marker = "[Suggested task id="

  static func encode(candidateID: String, description: String) -> String {
    "\(marker)\(candidateID)] \(description)"
  }

  static func parse(_ text: String) -> SuggestedTaskChatCard? {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix(marker), let close = trimmed.firstIndex(of: "]") else { return nil }
    let idStart = trimmed.index(trimmed.startIndex, offsetBy: marker.count)
    let candidateID = String(trimmed[idStart..<close]).trimmingCharacters(in: .whitespacesAndNewlines)
    let description = String(trimmed[trimmed.index(after: close)...])
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !candidateID.isEmpty, !description.isEmpty else { return nil }
    return SuggestedTaskChatCard(candidateID: candidateID, description: description)
  }
}

/// Chat presentation of a suggested task. Mirrors `ChatProactivePushRow`'s chrome so
/// the two read as one family, and adds the single action that matters.
struct ChatSuggestedTaskRow: View {
  let card: SuggestedTaskChatCard

  @State private var isAdded = false
  @State private var isAdding = false
  @State private var failed = false

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      Image(systemName: "checklist")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.secondary)
        .frame(width: 24, height: 24)
        .background(Ink.rowFill, in: Circle())
        .accessibilityHidden(true)
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text("Suggested task")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundColor(Ink.secondary)
        Text(card.description)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.primary)
          .textSelection(.enabled)
        if failed {
          Text("That didn't sync. Try again.")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
        }
        Button {
          add()
        } label: {
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: isAdded ? "checkmark" : "plus")
            Text(isAdded ? "Added to Tasks" : "Add to Tasks")
          }
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(isAdded ? Ink.listeningGreen : Ink.primary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(Ink.rowFillHover)
          )
        }
        .buttonStyle(.plain)
        .disabled(isAdded || isAdding)
        .opacity(isAdding ? 0.5 : 1)
        .accessibilityIdentifier("chat-suggested-task-add")
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
    .accessibilityLabel("Suggested task: \(card.description)")
  }

  private func add() {
    guard !isAdded, !isAdding else { return }
    isAdding = true
    failed = false
    Task { @MainActor in
      let store = SuggestedTasksStore.shared
      // A card can outlive the loaded page (reopened history), so make sure the
      // candidate set is present before resolving against it.
      if store.candidates.isEmpty {
        await store.load()
      }
      let taskID = await store.doNow(candidateID: card.candidateID, editedTitle: nil)
      isAdding = false
      if taskID != nil {
        isAdded = true
      } else {
        failed = true
      }
    }
  }
}

/// **How a turn that stopped mid-sentence tells the reader it was cut off.**
///
/// A voice barge-in persists whatever the assistant had said so far with a
/// terminal `.failed` status. Before this, a truncated answer rendered exactly
/// like a complete one — "…arrive on Saturday," with nothing to say it was
/// interrupted — because the only failure affordance was a stamp for a row
/// with no text at all.
enum ChatTurnFailurePresentation: Equatable {
  /// Not a failed assistant row.
  case none
  /// The turn failed with nothing to show: the row is the notice.
  case emptyTurnStamp
  /// The turn failed after saying something: show it, then mark the cut.
  case truncatedAnswer

  static func of(_ message: ChatMessage) -> Self {
    guard message.sender == .ai, !message.isStreaming, message.journalStatus == .failed else {
      return .none
    }
    guard message.text.isEmpty, message.contentBlocks.isEmpty else { return .truncatedAnswer }
    return .emptyTurnStamp
  }
}
