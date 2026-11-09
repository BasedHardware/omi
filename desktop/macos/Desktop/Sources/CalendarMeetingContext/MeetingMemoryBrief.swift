import Foundation

/// Calendar identity retained by a conversation, never inferred from its generated title.
struct ConversationMeetingIdentity: Equatable {
  let eventID: String
  let source: String
  let title: String
  let attendeeEmails: Set<String>

  init(eventID: String, source: String, title: String, attendeeEmails: Set<String>) {
    self.eventID = eventID.trimmingCharacters(in: .whitespacesAndNewlines)
    self.source = source.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    self.title = title.trimmingCharacters(in: .whitespacesAndNewlines)
    self.attendeeEmails = Set(attendeeEmails.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() })
      .subtracting([""])
  }

  init?(calendarContext raw: Any?) {
    guard let raw = raw as? [String: Any], let title = raw["title"] as? String else { return nil }
    let attendees = raw["participants"] as? [[String: Any]] ?? []
    self.init(
      eventID: raw["calendar_event_id"] as? String ?? "",
      source: raw["calendar_source"] as? String ?? "",
      title: title,
      attendeeEmails: Set(attendees.compactMap { $0["email"] as? String }))
  }

  init(_ link: OmiAPI.CalendarEventLink) {
    self.init(
      eventID: link.eventId,
      source: "google_calendar",
      title: link.title,
      attendeeEmails: Set(link.attendeeEmails ?? []))
  }
}

struct MeetingMemoryBriefFact: Equatable, Identifiable {
  enum Kind: Equatable {
    case decision
    case followUp
    case openQuestion

    var label: String {
      switch self {
      case .decision: return "Decided"
      case .followUp: return "Last recorded follow-up"
      case .openQuestion: return "Open question last time"
      }
    }
  }

  let kind: Kind
  let text: String
  let sourceConversationID: String
  let sourceSegmentIDs: [String]

  var id: String { "\(sourceConversationID):\(kind.label)" }
}

struct MeetingMemoryBrief: Equatable {
  let eventID: String
  let title: String
  let startsAt: Date
  let sourceConversationID: String
  let sourceConversationTitle: String
  let facts: [MeetingMemoryBriefFact]
}

/// A conservative, no-model pilot. Weak identity yields no brief, not a plausible-looking guess.
enum MeetingMemoryBriefComposer {
  static let lookback: TimeInterval = 180 * 24 * 60 * 60
  static let leadWindow: TimeInterval = 2 * 60 * 60

  static func compose(
    events: [SystemCalendarEventSnapshot],
    conversations: [ServerConversation],
    now: Date
  ) -> MeetingMemoryBrief? {
    let upcoming =
      events
      .filter {
        !$0.isAllDay && !$0.isCanceled && $0.startTime > now
          && $0.startTime.timeIntervalSince(now) <= leadWindow && $0.endTime > $0.startTime
      }
      .sorted { $0.startTime < $1.startTime }

    for event in upcoming {
      let previous =
        conversations
        .filter { conversation in
          guard
            !conversation.discarded && !conversation.deleted && !conversation.isLocked
              && !conversation.deferred && conversation.status == .completed,
            let identity = conversation.meetingIdentity
          else { return false }
          let capturedAt = conversation.startedAt ?? conversation.createdAt
          guard capturedAt < event.startTime,
            event.startTime.timeIntervalSince(capturedAt) <= lookback
          else { return false }
          return matches(event: event, identity: identity)
        }
        .sorted { ($0.startedAt ?? $0.createdAt) > ($1.startedAt ?? $1.createdAt) }

      for source in previous {
        let facts = facts(from: source)
        guard !facts.isEmpty else { continue }
        return MeetingMemoryBrief(
          eventID: event.calendarEventID,
          title: event.title,
          startsAt: event.startTime,
          sourceConversationID: source.id,
          sourceConversationTitle: source.displayTitle,
          facts: facts)
      }
      if !previous.isEmpty {
        // Counts only: the pilot's "why is my brief empty?" is otherwise silent.
        log(
          "MeetingMemoryBrief: \(previous.count) matched meeting(s) had no cited decision, follow-up, or open question")
      }
    }
    return nil
  }

  /// Normalized characters a title needs before title + attendee may match without an event ID.
  static let minimumTitleOnlyMatchLength = 8

  static func matches(event: SystemCalendarEventSnapshot, identity: ConversationMeetingIdentity) -> Bool {
    let eventID = event.calendarEventID.trimmingCharacters(in: .whitespacesAndNewlines)
    if !eventID.isEmpty && eventID == identity.eventID && identity.source == "system_calendar" {
      return true
    }

    // Without the same event ID, a short generic title ("Sync", "1:1") shared with one
    // attendee is too weak to tell recurring meetings apart, so it yields no brief.
    let title = normalizedTitle(event.title)
    guard title.count >= minimumTitleOnlyMatchLength, title == normalizedTitle(identity.title) else { return false }
    let eventEmails = Set(
      event.participants.compactMap { $0.email?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() })
    return !eventEmails.intersection(identity.attendeeEmails).isEmpty
  }

  private static func normalizedTitle(_ title: String) -> String {
    title.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
      .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
      .joined(separator: " ")
  }

  static func facts(from conversation: ServerConversation) -> [MeetingMemoryBriefFact] {
    var facts: [MeetingMemoryBriefFact] = []
    let sections = conversation.structured.sections

    // A "Decisions" heading is the strongest signal. Summaries usually title sections by
    // topic instead, so otherwise take the first cited line that states the outcome itself.
    func appendSection(
      _ kind: MeetingMemoryBriefFact.Kind, heading words: [String], headingLine accepts: (String) -> Bool,
      line states: (String) -> Bool
    ) {
      let cited = sections.filter { !$0.sourceSegmentIDs.isEmpty }
      let byHeading = cited.first { section in words.contains(where: section.heading.lowercased().contains) }
        .flatMap { section in cleanedLines(section.bodyMarkdown).first(where: accepts).map { (section, $0) } }
      let byLine = cited.compactMap { section in
        cleanedLines(section.bodyMarkdown).first(where: states).map { (section, $0) }
      }.first
      guard let (section, text) = byHeading ?? byLine else { return }
      facts.append(
        MeetingMemoryBriefFact(
          kind: kind, text: cardExcerpt(text), sourceConversationID: conversation.id,
          sourceSegmentIDs: section.sourceSegmentIDs))
    }

    // A "Decisions" heading admits imperative lines ("Ship the pilot first"), but the same
    // veto as the text fallback still drops anything unsettled or disputed.
    appendSection(
      .decision, heading: ["decision", "agreed"], headingLine: { !isUnsettled($0) }, line: statesDecision)
    if let action = conversation.structured.actionItems.first(where: {
      !$0.completed && !$0.deleted && $0.captureOwner == "user" && !$0.sourceSegmentIDs.isEmpty
    }), let text = firstLine(action.description) {
      facts.append(
        MeetingMemoryBriefFact(
          kind: .followUp, text: cardExcerpt(text), sourceConversationID: conversation.id,
          sourceSegmentIDs: action.sourceSegmentIDs))
    }
    appendSection(
      .openQuestion, heading: ["open question", "unresolved"], headingLine: { _ in true }, line: statesOpenQuestion)

    return Array(facts.prefix(3))
  }

  /// Card lines are compact; classification always reads the whole line first.
  private static let cardTextLimit = 240

  /// A long line is cut at the last word that fits and marked with an ellipsis, never mid-word.
  static func cardExcerpt(_ text: String) -> String {
    guard text.count > cardTextLimit else { return text }
    let cut = text.prefix(cardTextLimit - 1)
    let atWord = cut.lastIndex(where: \.isWhitespace).map { cut[..<$0] } ?? cut
    return atWord.trimmingCharacters(in: .whitespaces.union(.punctuationCharacters)) + "\u{2026}"
  }
  private static let openQuestionPhrases = ["open question", "unresolved", "undecided", "left open", "still open"]
  private static let outcomeWords = ["decided", "agreed", "decision"]
  /// Verbs that report an outcome as settled. "decision" alone is not one: "We will discuss
  /// the decision next week" mentions a decision that has not been made.
  private static let settledWords = ["decided", "agreed", "chose", "chosen", "approved", "settled", "finalized"]
  /// Words that put an outcome in the future, a hypothetical, or an obligation when they come
  /// just before its verb: "will be approved", "would have approved", "needs to be finalized".
  private static let unrealizedMarkers: Set<String> = [
    "will", "would", "shall", "should", "could", "might", "may", "must", "can", "going", "gonna", "to",
  ]
  private static let disputeMarkers = ["disagree", "objected", "pushed back", "dispute"]
  /// Discussion, proposals and questions are not outcomes.
  private static let uncertaintyMarkers = [
    "?", "discuss", "revisit", "tbd", "to be decided", "to be determined", "whether", "propose", "proposal",
    "suggest", "maybe", "might", "pending",
  ]
  private static let negations: Set<String> = [
    "not", "no", "never", "nothing", "nobody", "none", "neither", "nor", "without",
  ]

  private static func words(_ line: String) -> [String] {
    line.lowercased().split(whereSeparator: { !$0.isLetter && $0 != "'" && $0 != "\u{2019}" }).map(String.init)
  }

  private static func isNegation(_ word: String) -> Bool {
    negations.contains(word) || word.hasSuffix("n't") || word.hasSuffix("n\u{2019}t")
  }

  /// "not"/"never" directly between a settled verb and its "to" ("agreed not to"), or
  /// directly after that "to" ("agreed to not"): the outcome is settled, its action negative.
  private static func negatesSettledAction(_ tokens: [String], at index: Int) -> Bool {
    guard ["not", "never"].contains(tokens[index]) else { return false }
    let settled = Set(settledOutcomeIndices(tokens))
    if settled.contains(index - 1), index + 1 < tokens.count, tokens[index + 1] == "to" { return true }
    return index >= 2 && tokens[index - 1] == "to" && settled.contains(index - 2)
  }

  /// "We have not yet decided on pricing" and "No decision on hosting" are open questions:
  /// a negation before the outcome word. "They agreed not to ship" negates the action, not
  /// the agreement, so it is a decision (`isUnsettled`), never an open question.
  static func statesOpenQuestion(_ line: String) -> Bool {
    if openQuestionPhrases.contains(where: line.lowercased().contains) { return true }
    let tokens = words(line)
    guard let outcome = tokens.firstIndex(where: { word in outcomeWords.contains(where: word.hasPrefix) }) else {
      return false
    }
    return tokens[..<outcome].contains(where: isNegation)
  }

  /// The shared veto for both the heading path and the text fallback: any negation, dispute,
  /// discussion, proposal, question, or open-question wording. Ambiguous lines are omitted.
  /// The one negation that does not veto is the agreed action's own: "agreed not to ask",
  /// "decided never to ship", "chose to not renew" settle what will not happen.
  static func isUnsettled(_ line: String) -> Bool {
    let lower = line.lowercased()
    let tokens = words(line)
    return tokens.indices.contains { isNegation(tokens[$0]) && !negatesSettledAction(tokens, at: $0) }
      || disputeMarkers.contains(where: lower.contains)
      || uncertaintyMarkers.contains(where: lower.contains) || statesOpenQuestion(line)
      || reportsUnrealizedOutcome(line)
  }

  /// A settled outcome only, named by a settled verb and passing the shared veto.
  static func statesDecision(_ line: String) -> Bool {
    !settledOutcomeIndices(words(line)).isEmpty && !isUnsettled(line)
  }

  /// Where a settled verb ("approved"), or "made/reached a/the decision", names an outcome.
  private static func settledOutcomeIndices(_ tokens: [String]) -> [Int] {
    tokens.indices.filter { index in
      if settledWords.contains(tokens[index]) { return true }
      guard ["made", "reached"].contains(tokens[index]), index + 2 < tokens.count else { return false }
      return ["a", "the"].contains(tokens[index + 1]) && tokens[index + 2] == "decision"
    }
  }

  /// "The budget will be approved", "We will have decided by Friday", "We would have approved
  /// it": the verb is governed by an auxiliary in the few words before it, so nothing has been
  /// settled yet. A later "will" ("We agreed we will ship Thursday") reports a settled agreement.
  static func reportsUnrealizedOutcome(_ line: String) -> Bool {
    let tokens = words(line)
    return settledOutcomeIndices(tokens).contains { index in
      tokens[max(0, index - 3)..<index].contains { word in
        unrealizedMarkers.contains(word) || word.hasSuffix("'ll") || word.hasSuffix("\u{2019}ll")
          || word.hasSuffix("'d") || word.hasSuffix("\u{2019}d")
      }
    }
  }

  private static func cleanedLines(_ text: String) -> [String] {
    text.split(whereSeparator: \.isNewline).compactMap { raw in
      let cleaned = raw.trimmingCharacters(in: CharacterSet(charactersIn: " \t-*#•"))
      return cleaned.isEmpty ? nil : cleaned
    }
  }

  private static func firstLine(_ text: String) -> String? {
    cleanedLines(text).first
  }
}

/// Review-only text from explicit, cited user commitments in one completed meeting.
/// No recipient is inferred and nothing is sent by this composer.
enum MeetingFollowUpDraftComposer {
  static func compose(from conversation: ServerConversation) -> String? {
    guard
      !conversation.discarded && !conversation.deleted && !conversation.isLocked
        && !conversation.deferred && conversation.status == .completed
        && conversation.meetingIdentity != nil
    else { return nil }

    let actions = conversation.structured.actionItems
      .filter {
        !$0.completed && !$0.deleted && $0.captureOwner == "user" && !$0.sourceSegmentIDs.isEmpty
      }
      .compactMap { action -> String? in
        // The editable draft keeps every word: dates, links and qualifiers ("do not send
        // until legal approves") must survive into what the user reviews and copies.
        let text = action.description.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
      }
    guard !actions.isEmpty else { return nil }

    let bulletList = actions.map { "- \($0)" }.joined(separator: "\n")
    return
      "Thanks for the conversation. Here are the follow-ups I noted:\n\n\(bulletList)\n\nPlease let me know if I missed anything."
  }
}
