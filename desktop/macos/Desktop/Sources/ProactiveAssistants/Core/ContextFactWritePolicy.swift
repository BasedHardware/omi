import Foundation

/// What the deterministic write-time policy decided for one extracted statement.
enum ContextFactWriteVerdict: Equatable, Sendable {
  /// Stored unchanged.
  case pass
  /// Not stored at all: extraction machinery echoed back as content.
  case dropMachinery
  /// Stored, but notify-worthiness forced to 0 so it can never arm a candidate,
  /// clear a pooling floor, or trigger departure evaluation.
  case capScenery
  /// Stored, with notify-worthiness floored to arming eligibility.
  case floorHumanEvent
}

/// Deterministic write-time fact policy. Prompt instruction alone was measured
/// not to move scenery: after the extraction contract explicitly banned
/// "an app/window/tab is open/visible/shows" statements, the live scenery share
/// moved 34% -> 32% (noise), and the banned shape kept clearing the 0.6 arming
/// cut verbatim. Rejecting scenery is a much easier task than ranking it, so the
/// enforcement lives here, where the model cannot ignore it.
///
/// Three rules, applied in order:
///
/// 1. Machinery echoes are dropped. "The destination is unknown/." (the
///    destination-abstention instruction extracted as content) armed a live
///    candidate slot at 0.6; schema field names and prompt phrases have leaked
///    the same way.
/// 2. Named-person speech-acts are floored to arming eligibility. The new
///    extraction contract produces this class (9 in the first 108 facts vs 2 in
///    the prior 1,961) and nano scores it 0.0 in 8 of 9 — a Slack thread with a
///    reported bug, an acknowledgement from a named teammate, and a recurrence
///    all scored 0.0 while a sidebar description scored 0.7. The detector
///    requires a capitalized name immediately before a speech verb; on the full
///    2,069-fact corpus it fired 11 times, all genuine speech-acts.
/// 3. Scenery-shaped statements are capped to worthiness 0 but still stored:
///    they remain honest context for the director, they just can never arm.
///
/// Fitted on the pre-2026-08-16T17:33 corpus; on the held-out post-cut window
/// (n=108, hand-labeled) it capped 63/86 scenery statements, wrongly capped 1/8
/// actionable statements (an alert phrased "is present in the feed", which
/// scored 0.0 anyway), touched 0 human-event statements incorrectly, and turned
/// the arming mix from {scenery 11, actionable 4, human 1, machinery 1} into
/// {human 9, actionable 4, scenery 2}.
enum ContextFactWritePolicy {
  static let humanEventWorthinessFloor = 0.6

  /// Extraction machinery observed echoed back as statements in live data.
  private static let machineryPatterns: [String] = [
    #"unknown/"#,
    #"^The destination\b"#,
    #"notify_worthiness|evidence_refs|evidence_text|bucket_entry_refs|fact_ids"#,
    #"150-400|token summary|discrete factual records"#,
    #"(?i)untrusted screen|quoted data|screen-derived"#,
  ]

  private static let uiNoun =
    "(?:screen|window|tab|tabs|page|panel|pane|sidebar|interface|navigation|inbox|workspace"
    + "|browser|app|application|dashboard|view|list|menu|button|section|sections|header|feed"
    + "|chart|charts|column|columns|thread|dialog|prompt|editor|area|layout|theme|avatar|icon"
    + "|label|labels|folder|folders)"

  /// Display-language shapes. Deliberately does not include a bare "is present"
  /// (only "is present in"): "A remediation instruction is present to repair
  /// the surface" is an action item, and bare "present" was the one pattern
  /// that wrongly capped it during held-out evaluation.
  private static let sceneryPatterns: [String] = [
    #"\b(?:is|are|was|were|remains?)\s+(?:currently\s+|now\s+|being\s+)?(?:open|opened|visible|displayed|shown|active|highlighted|listed|in focus|in use|in view|on screen|viewed|used|read|displaying|showing)\b"#,
    #"\b(?:is|are)\s+(?:viewing|browsing|reviewing|looking at|reading|scrolling|preparing to type|interacting with|working within|signed in)\b"#,
    "(?i)^(?:the|a|an)?\\s*(?:[A-Z][\\w.-]*\\s+)?(?:left\\s+|right\\s+|top\\s+|bottom\\s+|main\\s+)?"
      + uiNoun
      + "\\b[^.]{0,60}?\\b(?:shows?|showing|displays?|displaying|lists?|listing|contains?|containing|includes?|including|features?|indicates?|presents?|offers?|suggests?|suggesting)\\b",
    "\\b(?:shows?|displays?)\\s+(?:a|an|the|multiple|various|several)?\\s*[^.]{0,40}?" + uiNoun
      + "\\b",
    #"(?i)\b(?:unread|new)\s+(?:messages?|items?|notifications?)\b"#,
    #"(?i)\b(?:appears?|is present|are present)\s+in\b"#,
    #"(?i)\bwindow (?:titled|named|labeled)\b"#,
    #"(?i)\b(?:email|message)s?\b[^.]{0,80}\b(?:in the inbox|is listed|are listed|in the list)\b"#,
    #"(?i)^(?:the\s+)?active (?:window|tab|app)\b"#,
  ]

  private static let speechVerbs =
    "(?:posted|replied|thanked|asked|asks|acknowledged|acknowledges|reported|noted|mentioned"
    + "|mentions|said|says|stated|states|requested|promised|agreed|confirmed|committed|shared"
    + "|flagged|announced|proposed|wrote|commented|responded)"

  /// Capitalized tokens that look like names but are sentence subjects of
  /// system/scenery prose ("Review notes reference…", "Release notes mention…").
  private static let speechSubjectStopWords: Set<String> = [
    "The", "A", "An", "There", "This", "That", "User", "Screen", "Window", "Review",
    "Release", "Discussion", "Documentation", "Notes", "Summary", "Context", "Conversation",
    "Conversations", "Chats", "Application", "Communication", "Discord", "Chrome", "Google",
    "Slack", "Gmail", "Telegram", "Finder", "Cursor", "Claude", "Grok", "Two", "Several",
    "Some", "One", "All", "Rules", "Overall", "Right", "Left", "Workspace", "Repository",
    "Task", "Tasks", "Earlier", "Ongoing", "Block",
  ]

  private static let humanEventRegex: NSRegularExpression? = try? NSRegularExpression(
    pattern:
      "\\b([A-Z][a-z]{2,}(?:\\s+[A-Z][a-z]{2,})?)\\s+(?:also\\s+|then\\s+|again\\s+|later\\s+)?"
      + speechVerbs + "\\b")

  static func verdict(_ statement: String) -> ContextFactWriteVerdict {
    let trimmed = statement.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .dropMachinery }
    if matchesAny(machineryPatterns, in: trimmed) { return .dropMachinery }
    if isHumanEvent(trimmed) { return .floorHumanEvent }
    if matchesAny(sceneryPatterns, in: trimmed) { return .capScenery }
    return .pass
  }

  /// A capitalized name immediately before a speech verb, where the name is not
  /// a known scenery subject. Checked before scenery so display phrasing later
  /// in the sentence cannot cap a genuine speech-act.
  static func isHumanEvent(_ statement: String) -> Bool {
    guard let regex = humanEventRegex else { return false }
    let range = NSRange(statement.startIndex..., in: statement)
    var found = false
    regex.enumerateMatches(in: statement, range: range) { match, _, stop in
      guard let match, let nameRange = Range(match.range(at: 1), in: statement) else { return }
      let firstToken = statement[nameRange].split(separator: " ").first.map(String.init) ?? ""
      if !speechSubjectStopWords.contains(firstToken) {
        found = true
        stop.pointee = true
      }
    }
    return found
  }

  private static func matchesAny(_ patterns: [String], in statement: String) -> Bool {
    patterns.contains { statement.range(of: $0, options: .regularExpression) != nil }
  }
}
