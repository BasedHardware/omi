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
    }
    return nil
  }

  static func matches(event: SystemCalendarEventSnapshot, identity: ConversationMeetingIdentity) -> Bool {
    let eventID = event.calendarEventID.trimmingCharacters(in: .whitespacesAndNewlines)
    if !eventID.isEmpty && eventID == identity.eventID && identity.source == "system_calendar" {
      return true
    }

    let title = normalizedTitle(event.title)
    guard title.count >= 8, title == normalizedTitle(identity.title) else { return false }
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

    func appendSection(_ kind: MeetingMemoryBriefFact.Kind, matching words: [String]) {
      guard
        let section = sections.first(where: { section in
          let heading = section.heading.lowercased()
          return !section.sourceSegmentIDs.isEmpty && words.contains(where: heading.contains)
        }), let text = firstLine(section.bodyMarkdown)
      else { return }
      facts.append(
        MeetingMemoryBriefFact(
          kind: kind, text: text, sourceConversationID: conversation.id,
          sourceSegmentIDs: section.sourceSegmentIDs))
    }

    appendSection(.decision, matching: ["decision", "agreed"])
    if let action = conversation.structured.actionItems.first(where: {
      !$0.completed && !$0.deleted && $0.captureOwner == "user" && !$0.sourceSegmentIDs.isEmpty
    }), let text = firstLine(action.description) {
      facts.append(
        MeetingMemoryBriefFact(
          kind: .followUp, text: text, sourceConversationID: conversation.id,
          sourceSegmentIDs: action.sourceSegmentIDs))
    }
    appendSection(.openQuestion, matching: ["open question", "unresolved"])

    return Array(facts.prefix(3))
  }

  private static func firstLine(_ text: String) -> String? {
    guard
      let raw = text.split(whereSeparator: \.isNewline).first(where: {
        !$0.trimmingCharacters(in: .whitespaces).isEmpty
      })
    else {
      return nil
    }
    let cleaned = raw.trimmingCharacters(in: CharacterSet(charactersIn: " \t-*#"))
    guard !cleaned.isEmpty else { return nil }
    return String(cleaned.prefix(240))
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
        let text = action.description.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : String(text.prefix(240))
      }
    guard !actions.isEmpty else { return nil }

    let bulletList = actions.map { "- \($0)" }.joined(separator: "\n")
    return
      "Thanks for the conversation. Here are the follow-ups I noted:\n\n\(bulletList)\n\nPlease let me know if I missed anything."
  }
}
