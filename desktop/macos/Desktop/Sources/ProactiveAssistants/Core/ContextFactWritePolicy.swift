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

  /// A user-authored question is only answerable NOW: a question fact that
  /// outlives its compose moment lets a later departure evaluation force
  /// retrieval for a question no longer on screen and deliver the wrong
  /// answer (seen live: a stale ask answered instead of the current one).
  /// Ten minutes covers grace retries and slow evaluations; a re-ask
  /// re-validates through the expiry-aware duplicate check.
  static let userQuestionFactTTLSeconds: TimeInterval = 600

  /// Extraction machinery observed echoed back as statements in live data.
  ///
  /// Every pattern is anchored to the echo it was measured on. Unanchored
  /// substrings are unsafe here because this verdict skips the INSERT entirely:
  /// a bare `unknown/` also deletes "Push to unknown/production failed.", and a
  /// bare `150-400` also deletes "Latency is 150-400ms at p99." Dropping a real
  /// fact is worse than storing a machinery echo, so the cost of a miss is
  /// deliberately lower than the cost of a false positive.
  private static let machineryPatterns: [String] = [
    #"(?i)^\W*the destination is unknown/"#,
    #"(?i)untrusted screen-derived content"#,
    #"\b(?:notify_worthiness|evidence_refs|evidence_text|bucket_entry_refs|fact_ids)\b"#,
    #"(?i)\b150-400 token summary\b"#,
    #"(?i)\bdiscrete factual records\b"#,
    // The prompt's own Good/Bad examples. Examples leak verbatim on this model
    // (~1 in 14 calls). The Good example is a named-person speech-act, which is
    // exactly the class `floorHumanEvent` promotes to arming eligibility — so a
    // leaked example would not merely be stored, it would arm a notification.
    #"(?i)^\W*nik asked for the demo recording before tomorrow's launch video"#,
    #"(?i)^\W*the user is asking alex@example\.com"#,
    #"(?i)^\W*the user is viewing a window with a sidebar and a chat panel"#,
    #"(?i)^\W*ambient narrative:"#,
  ]

  /// Pure interface chrome. A sentence *about* one of these is a description of
  /// the display, whatever else it says.
  ///
  /// Content-bearing nouns a screen merely happens to render — thread, list,
  /// feed, chart, inbox, editor, dashboard, column, folder, section — are
  /// deliberately NOT here. "The chart shows error rate above the SLO" and "The
  /// thread shows Nik asked for the recording" carry the payload in the object,
  /// not the subject, and capping them silently zeroes a real signal. Missing
  /// some scenery is the intended trade: everything here still reaches the
  /// director, so a miss costs noise, while a false positive costs a fact.
  private static let chromeNoun =
    "(?:screen|window|tab|tabs|page|panel|pane|sidebar|interface|navigation|workspace"
    + "|browser|app|application|view|menu|button|header|toolbar|dialog|prompt|layout"
    + "|theme|avatar|icon)"

  /// Display-language shapes, each anchored to an interface subject rather than
  /// to a bare copula.
  ///
  /// The unanchored earlier form matched the *phrase* "is open" / "appears in"
  /// anywhere in a sentence, which is ordinary English for work status:
  /// "PR #11651 is open and blocked on review", "The feature flag is now active
  /// in production", "Legal is reviewing the MSA before Friday" and "The
  /// regression appears in the latest build" were all capped to worthiness 0.
  /// The extraction prompt bans a *subject* ("an app, window, tab … is open"),
  /// so the enforcement matches that predicate and not the verb alone.
  private static let sceneryPatterns: [String] = [
    // "The user is viewing / browsing / reading …" — the observer framing.
    #"(?i)\b(?:the\s+)?user\s+(?:is|was)\s+(?:currently\s+|now\s+)?(?:viewing|browsing|reviewing|looking at|reading|scrolling|preparing to type|interacting with|working within|signed in|using)\b"#,
    // An interface subject in an open/visible/active state.
    "(?i)^\\W*(?:the|a|an)?\\s*[^.]{0,60}?\\b" + chromeNoun
      + "\\b[^.]{0,60}?\\b(?:is|are|was|were|remains?)\\s+(?:currently\\s+|now\\s+|being\\s+)?"
      + "(?:open|opened|visible|displayed|shown|active|highlighted|in focus|in use|in view"
      + "|on screen|present)\\b",
    // An interface subject doing the displaying.
    "(?i)^\\W*(?:the|a|an)?\\s*(?:[A-Z][\\w.-]*\\s+)?(?:left\\s+|right\\s+|top\\s+|bottom\\s+|main\\s+)?"
      + chromeNoun
      + "\\b[^.]{0,60}?\\b(?:shows?|showing|displays?|displaying|lists?|listing|contains?|containing|includes?|including|features?|indicates?|presents?|offers?|suggests?|suggesting)\\b",
    #"(?i)\b(?:unread|new)\s+(?:messages?|items?|notifications?)\b"#,
    // Only "appears in <the interface>", never a bare "appears in": a
    // regression appearing in a build is an event, not a description.
    "(?i)\\b(?:appears?|is present|are present)\\s+in\\s+(?:the\\s+|a\\s+|an\\s+)?[^.]{0,30}?\\b"
      + chromeNoun + "\\b",
    #"(?i)\bwindow (?:titled|named|labeled)\b"#,
    #"(?i)^\W*(?:the\s+)?active (?:window|tab|app)\b"#,
    // "… is open in a tab within a browser": the subject is ordinary content,
    // but the state verb is qualified by where on the display it sits. Anchored
    // on the location phrase, so "PR #11651 is open and blocked on review"
    // (no interface location) is untouched.
    "(?i)\\b(?:is|are|was|were)\\s+(?:currently\\s+|now\\s+)?"
      + "(?:open|opened|visible|displayed|shown|active|highlighted)\\s+(?:in|on|within|under)\\s+"
      + "(?:a|an|the)?\\s*[^.]{0,30}?\\b" + chromeNoun + "\\b",
    // "Finder is being used." — bare app-usage narration with no object. Kept
    // sentence-final so "The staging cluster is being used for the load test"
    // (which says what for) still passes.
    #"(?i)\bis being (?:used|viewed|displayed|shown)\s*\.?\s*$"#,
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

  // MARK: - Prompt-echo detection
  //
  // The anchored machinery patterns above catch near-verbatim echoes; live data
  // shows the model also *paraphrases* its instructions into facts — "The
  // designated destination value is set to unknown/.", "If domain confidence is
  // low, the response should be unknown/.", "The user requires that each factual
  // record be a plain declarative sentence." — 77 such statements in the 2,531-
  // fact corpus this was fitted on, every one a genuine echo on reading. The
  // detector is deliberately conjunctive so no single pattern can delete a real
  // fact: an *instruction-reporting frame* (a subject like user/task/instructions
  // followed by a requesting verb) must co-occur with *prompt-specific
  // vocabulary* (terms that exist only in these prompts). Negatives verified to
  // pass: "Push to unknown/production failed." (vocabulary, no frame), "The
  // response should be sent to the customer before EOD." (frame, no vocabulary),
  // "The destination branch cannot fast-forward." (neither).

  /// Terms that occur in the extraction/destination prompts and essentially
  /// nowhere in real work prose.
  /// `unknown/` sits outside the word-boundary group: the slash is already a
  /// delimiter, and a trailing `\b` cannot match between `/` and end-of-sentence
  /// punctuation, which made "… should be unknown/." invisibly unmatched.
  private static let echoVocabularyPattern =
    #"(?i)(?:\bunknown/|\b(?:page-group|evidence_refs|evidence_text|notify_worthiness"#
    + #"|token summary|factual records?|declarative sentences?|on-screen wording"#
    + #"|site suffix|screen-derived|quoted data|domain/section|facts list"#
    + #"|evidence reference|handles copied|copied from (?:the )?(?:quoted )?on-screen)\b)"#

  /// "<instruction-ish subject> … <requesting verb>" within one clause.
  private static let echoFramePattern =
    #"(?i)\b(?:user|task|instructions?|rules?|content|output|format|prompt"#
    + #"|requirements?|response|statements?|records?|evidence(?: blocks?| text)?|summary)\b"#
    + #"[^.]{0,50}\b(?:requests?|requires?|required|instructed|instructs?|specif\w+"#
    + #"|demands?|asks?|must|should|needs? to|are to be|is to be)\b"#

  /// The destination-abstention echo family ("Destination is set to unknown/",
  /// "Direct instruction to set destination path to unknown/"). Requires the
  /// word "destination" (or an explicit "set to") near `unknown/`, so "Push to
  /// unknown/production failed." — a real fact containing the bare token — is
  /// untouched.
  private static let destinationEchoPatterns: [String] = [
    #"(?i)\bdestination\b[^.]{0,50}\bunknown/"#,
    #"(?i)\b(?:is|are|be|been)\s+set\s+to\b[^.]{0,25}\bunknown/"#,
  ]

  static func isPromptEcho(_ statement: String) -> Bool {
    if matchesAny(destinationEchoPatterns, in: statement) { return true }
    return statement.range(of: echoVocabularyPattern, options: .regularExpression) != nil
      && statement.range(of: echoFramePattern, options: .regularExpression) != nil
  }

  static func verdict(_ statement: String) -> ContextFactWriteVerdict {
    let trimmed = statement.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .dropMachinery }
    if matchesAny(machineryPatterns, in: trimmed) || isPromptEcho(trimmed) {
      return .dropMachinery
    }
    if isHumanEvent(trimmed) || isUserAuthoredQuestion(trimmed) { return .floorHumanEvent }
    if matchesAny(sceneryPatterns, in: trimmed) { return .capScenery }
    return .pass
  }

  /// A question the user is writing, recorded as a fact. This class seeds the
  /// answer-delivery path (dwell refresh -> departure evaluation -> retrieval
  /// hop), and nano scores it like scenery: the live fact "The body of the
  /// email currently contains the question: What is the latest omi desktop app
  /// download link?" arrived at worthiness 0.0, which kept the bucket
  /// ineligible and the departure trigger dark. Conjunctive on purpose: a
  /// question signal (a literal "?" or the word "question") must co-occur with
  /// an authoring/asking frame, so page content that merely displays a
  /// question ("the page shows a FAQ") never floors.
  static func isUserAuthoredQuestion(_ statement: String) -> Bool {
    // A strong asking verb with the user as subject IS the signal: extraction
    // freely paraphrases the typed question away from its punctuation and its
    // interrogative words ("The user is asking for a link to the latest Omi
    // desktop to be shared"), so requiring a separate question marker missed
    // real asks. Weak authoring verbs (writing/typing/composing/drafting)
    // still need an explicit question marker so ordinary composing never
    // floors.
    if statement.range(
      of:
        #"(?i)\b(?:the user|user)\b[^.]{0,40}\b(?:is asking|asks|asked|wants to know|is requesting|requests)\b"#,
      options: .regularExpression) != nil
    {
      return true
    }
    // Artifact-subject branches below must never classify RECEIVED content:
    // "An email from David contains the question: …" is someone else's ask.
    let receivedMarker =
      statement.range(
        of: #"(?i)\b(?:from|received|sender|sent by|reply from|inbox)\b"#,
        options: .regularExpression) != nil
    if !receivedMarker,
      statement.range(
        of: #"(?i)\b(?:body|draft|message|email)\b[^.]{0,60}\bcontains the question\b"#,
        options: .regularExpression) != nil
    {
      return true
    }
    // Passive draft-subject phrasings observed live: "A draft email is
    // addressed to david@… containing a question about …" and "A note or
    // message content questions the URL to download Omi for Mac." — the model
    // displaces the user subject onto the artifact, and both scored 0.0,
    // keeping the departure trigger dark. A draft that contains or poses a
    // question was authored by the user in every compose context this path
    // serves; received questions arrive as speech-acts ("David asked …").
    if !receivedMarker,
      statement.range(
        of:
          #"(?i)\b(?:draft|email|message|note|body|content)\b(?:[^.]|\.(?=\S)){0,70}\b(?:contain(?:s|ing)?|includes?|including|with)\b(?:[^.]|\.(?=\S)){0,40}\bquestion\b"#,
        options: .regularExpression) != nil
    {
      return true
    }
    if !receivedMarker,
      statement.range(
        of: #"(?i)\b(?:draft|email|message|note|body|text|content)\b[^.]{0,50}\bquestions\b"#,
        options: .regularExpression) != nil
    {
      return true
    }
    // Compose-anchored artifact-subject asking ("A message is being composed
    // to david@… asking for the latest Omi desktop link" — live, w=1.0, yet
    // unclassified). The compose anchor keeps received mail ("An email from
    // David asks …") out of this class.
    if statement.range(
      of:
        #"(?i)\b(?:draft|email|message|note)\b(?:[^.]|\.(?=\S)){0,40}\b(?:being (?:composed|drafted|written)|composed to|addressed to)\b(?:[^.]|\.(?=\S)){0,60}\b(?:asking|asks|requesting|requests)\b"#,
      options: .regularExpression) != nil
    {
      return true
    }
    // User-subject inclusion verbs ("The user included a question about the
    // latest Omi desktop link in the body of the email" — live, scored 0.9 by
    // the model yet unclassified here, so the forced lookup never armed).
    if statement.range(
      of:
        #"(?i)\b(?:the user|user)\b[^.]{0,40}\b(?:included|includes|including|added|adds|adding|embedded|embeds|posed|poses|posing|put|puts)\b[^.]{0,40}\bquestion\b"#,
      options: .regularExpression) != nil
    {
      return true
    }
    // Structural catch-all fitted after five distinct live paraphrases each
    // needed its own pattern: an artifact-subject statement carrying a literal
    // question mark ("The message body includes the line: 'what is the latest
    // Omi desktop link?'") is the user's own typed question unless the
    // statement marks the artifact as received.
    if statement.contains("?"),
      statement.range(
        of: #"(?i)\b(?:draft|email|message|note|body|compose|subject)\b"#,
        options: .regularExpression) != nil,
      statement.range(
        of: #"(?i)\b(?:from|received|sender|sent by|reply from|inbox)\b"#,
        options: .regularExpression) == nil
    {
      return true
    }
    let questionMarker =
      statement.contains("?")
      || statement.range(of: #"(?i)\bquestion\b"#, options: .regularExpression) != nil
    guard questionMarker else { return false }
    if statement.range(
      of:
        #"(?i)\b(?:the user|user)\b[^.]{0,40}\b(?:is writing|is typing|is composing|is drafting|wrote|writes|typed)\b"#,
      options: .regularExpression) != nil
    {
      return true
    }
    // Extraction sometimes mangles the subject ("Yu is composing a new email
    // ... What is the latest link?"): a literal question mark inside a
    // compose/draft-frame statement is still the user's own typed question —
    // received questions surface as speech-acts ("David asked ..."), not as
    // compose frames.
    return statement.contains("?")
      && statement.range(
        of: #"(?i)\b(?:composing|drafting|writing|typing)\b[^.]{0,60}\b(?:email|message|draft|reply)\b"#,
        options: .regularExpression) != nil
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

  /// An invalid pattern fails silently in both engines used here: `try?` leaves
  /// `humanEventRegex` nil, and `range(of:options:.regularExpression)` returns
  /// nil, so a broken rule reads exactly like a rule that never matches.
  /// Asserted by the tests so a typo cannot quietly disable enforcement.
  static var allPatternsCompile: Bool {
    humanEventRegex != nil
      && (machineryPatterns + sceneryPatterns + destinationEchoPatterns
        + [echoVocabularyPattern, echoFramePattern]).allSatisfy {
          (try? NSRegularExpression(pattern: $0)) != nil
        }
  }
}
