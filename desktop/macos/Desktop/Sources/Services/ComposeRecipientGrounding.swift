import Foundation

/// One chat turn as the grounding check sees it.
struct ComposeTranscriptTurn: Equatable, Sendable {
  let isPerson: Bool
  let text: String
  /// The text of a question-card answer is the option's `preparedAnswer`,
  /// written by the model; the person only clicked its label.
  let isQuestionCardAnswer: Bool

  init(isPerson: Bool, text: String, isQuestionCardAnswer: Bool = false) {
    self.isPerson = isPerson
    self.text = text
    self.isQuestionCardAnswer = isQuestionCardAnswer
  }

  @MainActor
  static func recentMainChatTurns(limit: Int = 20) -> [ComposeTranscriptTurn] {
    guard let messages = ChatProvider.mainInstance?.messages else { return [] }
    return messages.suffix(limit).map { message in
      ComposeTranscriptTurn(
        isPerson: message.sender == .user,
        text: message.text,
        isQuestionCardAnswer: message.clientTurnId?.hasPrefix("qri_") == true)
    }
  }
}

/// Decides whether a draft's recipient came from the person rather than from
/// something the model read or wrote.
///
/// The compose window has no "Omi wants to…" framing, so an address lifted
/// from a web page, an email or screen text would look like the person's own
/// draft. A recipient is grounded only when it appears in words the person
/// typed, pasted or dictated in this turn or the one before it in the same
/// chat, in a `search_contacts` result from the same run, or is the signed-in
/// account's own address. Anything else is sent back to the model to confirm
/// with the person, and no window opens.
@MainActor
final class ComposeRecipientGrounding {
  static let shared = ComposeRecipientGrounding()

  /// Runs remembered at once; older lookups fall out first.
  static let maxRememberedRuns = 32

  private struct RunHandles {
    let ownerID: String?
    var keys: Set<String>
  }

  private let accountEmail: () -> String?
  private var handlesByRun: [String: RunHandles] = [:]
  private var runOrder: [String] = []

  init(accountEmail: @escaping () -> String? = { AuthState.shared.userEmail }) {
    self.accountEmail = accountEmail
  }

  /// Remembers every phone number and email a contacts lookup returned, for
  /// the run that asked for it.
  func recordContactHandles(_ handles: [String], runID: String?, ownerID: String?) {
    guard let runID, !runID.isEmpty else { return }
    let keys = Set(handles.compactMap(Self.recipientKey))
    guard !keys.isEmpty else { return }
    if var existing = handlesByRun[runID], existing.ownerID == ownerID {
      existing.keys.formUnion(keys)
      handlesByRun[runID] = existing
      return
    }
    handlesByRun[runID] = RunHandles(ownerID: ownerID, keys: keys)
    runOrder.removeAll { $0 == runID }
    runOrder.append(runID)
    while runOrder.count > Self.maxRememberedRuns {
      handlesByRun.removeValue(forKey: runOrder.removeFirst())
    }
  }

  /// The recipients that did not come from the person, in their given order.
  /// `personTexts` holds only words the person wrote: see `personTexts(userText:transcript:)`.
  func ungroundedRecipients(
    _ recipients: [String],
    personTexts: [String],
    runID: String?,
    ownerID: String?
  ) -> [String] {
    var trusted: Set<String> = []
    for text in personTexts { trusted.formUnion(Self.recipientKeys(inPersonText: text)) }
    if let runID, let run = handlesByRun[runID], run.ownerID == ownerID {
      trusted.formUnion(run.keys)
    }
    if let email = accountEmail(), let key = Self.recipientKey(email) {
      trusted.insert(key)
    }
    return recipients.filter { recipient in
      guard let key = Self.recipientKey(recipient) else { return true }
      return !trusted.contains { Self.keysMatch(key, $0) }
    }
  }

  /// Forgets every lookup, for a sign-out or owner switch.
  func releaseAll() {
    handlesByRun.removeAll()
    runOrder.removeAll()
  }

  // MARK: - Whose words

  /// The person's own words for this run: the run's text, unless it was a
  /// question-card answer the model wrote, plus the person's one previous turn
  /// in the same chat so "yes, that address" can confirm a draft.
  ///
  /// The run text is matched to its chat turn by content. When no chat turn
  /// matches (task chat, voice), the run text stands alone: the voice run's
  /// text is the provider's transcript of what the person said.
  nonisolated static func personTexts(userText: String?, transcript: [ComposeTranscriptTurn]) -> [String] {
    guard let userText else { return [] }
    let runText = ChatToolExecutor.strippingRuntimeClockPreamble(userText)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !runText.isEmpty else { return [] }

    func trimmed(_ turn: ComposeTranscriptTurn) -> String {
      turn.text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    let personTurns = transcript.enumerated().filter { $0.element.isPerson && !trimmed($0.element).isEmpty }
    let currentIndex =
      personTurns.last { trimmed($0.element) == runText }?.offset
      ?? personTurns.last { runText.contains(trimmed($0.element)) }?.offset
    guard let currentIndex else { return [runText] }

    var texts: [String] = []
    if !transcript[currentIndex].isQuestionCardAnswer { texts.append(runText) }
    if let previous = personTurns.last(where: { $0.offset < currentIndex })?.element,
      !previous.isQuestionCardAnswer
    {
      texts.append(trimmed(previous))
    }
    return texts
  }

  // MARK: - Matching

  /// `e:<lowercased address>` or `p:<digits>`, or nil when the value holds neither.
  nonisolated static func recipientKey(_ value: String) -> String? {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.contains("@") {
      return trimmed.isEmpty ? nil : "e:" + trimmed.lowercased()
    }
    let digits = trimmed.filter { $0.isASCII && $0.isNumber }
    return digits.count >= 3 ? "p:" + digits : nil
  }

  /// Emails match exactly. Phone numbers match on the whole number: the same
  /// digits, or a national number of ten or more digits that the other side
  /// writes with a one-to-three-digit country code in front ("555 010 0100"
  /// and "+1 (555) 010-0100"). A shorter run of digits never matches part of a
  /// longer one.
  nonisolated static func keysMatch(_ lhs: String, _ rhs: String) -> Bool {
    if lhs == rhs { return true }
    guard lhs.hasPrefix("p:"), rhs.hasPrefix("p:") else { return false }
    let left = lhs.dropFirst(2)
    let right = rhs.dropFirst(2)
    let (shorter, longer) = left.count <= right.count ? (left, right) : (right, left)
    return shorter.count >= 10 && (1...3).contains(longer.count - shorter.count) && longer.hasSuffix(shorter)
  }

  private nonisolated static let emailPattern = #"[A-Za-z0-9._+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"#
  private nonisolated static let phonePattern = #"\+?[0-9][0-9 ().\-]*[0-9]"#
  /// Dates such as 2026-10-10 or 10.10.2026 are digits, not phone numbers.
  private nonisolated static let datePattern =
    #"^(?:\d{4}[-.]\d{1,2}[-.]\d{1,2}|\d{1,2}[-.]\d{1,2}[-.]\d{2,4})$"#
  /// A number right after one of these words is a reference, not a phone number.
  private nonisolated static let referencePattern =
    #"(?:#|\b(?:order|invoice|ticket|ref|reference|confirmation|tracking|account|booking|case)\b)[\s:#.]*(?:no\.?\s*)?$"#

  /// Every email address and phone-shaped number in words the person wrote.
  nonisolated static func recipientKeys(inPersonText text: String) -> Set<String> {
    var keys: Set<String> = []
    for (pattern, isPhone) in [(emailPattern, false), (phonePattern, true)] {
      guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
      let range = NSRange(text.startIndex..., in: text)
      for match in regex.matches(in: text, range: range) {
        guard let swiftRange = Range(match.range, in: text) else { continue }
        let token = String(text[swiftRange]).trimmingCharacters(in: .whitespaces)
        if isPhone,
          !isPhoneShaped(
            token, before: String(text[..<swiftRange.lowerBound]), after: text[swiftRange.upperBound...].first)
        {
          continue
        }
        if let key = recipientKey(token) { keys.insert(key) }
      }
    }
    return keys
  }

  private nonisolated static func isPhoneShaped(_ token: String, before: String, after: Character?) -> Bool {
    if token.range(of: datePattern, options: .regularExpression) != nil { return false }
    // A number glued to letters or an @ is part of a word or an address.
    let glue: (Character) -> Bool = { $0.isLetter || $0 == "@" || $0 == "_" || $0 == "." }
    if let last = before.last, glue(last) { return false }
    if let after, glue(after) || after.isNumber { return false }
    let lead = String(before.suffix(24)).lowercased()
    return lead.range(of: referencePattern, options: .regularExpression) == nil
  }
}
