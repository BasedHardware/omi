import Foundation

/// Why a `propose_*` call was refused before any window opened.
enum ComposeProposalRejection: Error, Equatable, Sendable {
  case emptyRecipient
  case tooManyRecipients(limit: Int)
  /// Looks like a person's name. Omi never turns a name into an address on its
  /// own; the model resolves it with `search_contacts` and asks when unsure.
  case recipientNeedsLookup(String)
  case invalidRecipient(String)
  /// A valid address that did not come from the person in this request.
  case recipientNeedsConfirmation([String])
  case emptyBody

  var reasonCode: String {
    switch self {
    case .emptyRecipient: return "empty_recipient"
    case .tooManyRecipients: return "too_many_recipients"
    case .recipientNeedsLookup: return "recipient_needs_lookup"
    case .invalidRecipient: return "invalid_recipient"
    case .recipientNeedsConfirmation: return "recipient_needs_confirmation"
    case .emptyBody: return "empty_body"
    }
  }
}

/// Turns tool arguments into a proposal, or says what is wrong with them.
enum ComposeProposalRequest {
  static let maxRecipients = 20

  static func parse(
    _ channel: ComposeProposalChannel,
    arguments: [String: Any]
  ) -> Result<ComposeProposal, ComposeProposalRejection> {
    // A bare string is accepted as one recipient, matching the iOS surface.
    let rawRecipients: [Any]
    if let single = arguments["to"] as? String {
      rawRecipients = [single]
    } else {
      rawRecipients = arguments["to"] as? [Any] ?? []
    }

    var recipients: [String] = []
    var seen: Set<String> = []
    for raw in rawRecipients {
      guard let text = raw as? String else { return .failure(.invalidRecipient(String(describing: raw))) }
      let candidate = text.trimmingCharacters(in: .whitespacesAndNewlines)
      if candidate.isEmpty { continue }
      guard let key = recipientKey(candidate, channel: channel) else {
        return .failure(looksLikeName(candidate) ? .recipientNeedsLookup(candidate) : .invalidRecipient(candidate))
      }
      if seen.insert(key).inserted { recipients.append(candidate) }
    }
    guard !recipients.isEmpty else { return .failure(.emptyRecipient) }
    guard recipients.count <= maxRecipients else { return .failure(.tooManyRecipients(limit: maxRecipients)) }

    guard let body = arguments["text"] as? String,
      !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else { return .failure(.emptyBody) }

    var subject: String?
    if channel == .email, let raw = arguments["subject"] as? String {
      // A subject is one header line; a newline in it is never intended.
      let flattened = raw.components(separatedBy: .newlines).joined(separator: " ")
        .trimmingCharacters(in: .whitespaces)
      subject = flattened.isEmpty ? nil : flattened
    }
    return .success(ComposeProposal(channel: channel, recipients: recipients, subject: subject, body: body))
  }

  /// Letters and no `@`: a person's name, not a malformed address.
  static func looksLikeName(_ value: String) -> Bool {
    !value.contains("@") && value.rangeOfCharacter(from: .letters) != nil
  }

  /// A normalized key for de-duplication, or nil when the value is not an
  /// address this channel can use.
  static func recipientKey(_ value: String, channel: ComposeProposalChannel) -> String? {
    if isEmailAddress(value) { return value.lowercased() }
    guard channel == .message, let digits = phoneDigits(value) else { return nil }
    return digits
  }

  /// A deliberately narrow ASCII form. No `mailto:` URL is built today, but
  /// `?`, `&`, `%`, `/` or `#` in an address would become header injection the
  /// day one is, and a lookalike Unicode domain is never what the person meant.
  private static let emailPattern =
    #"^[A-Za-z0-9_+\-]+(?:\.[A-Za-z0-9_+\-]+)*@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?\.)+(?:[A-Za-z]{2,}|xn--[A-Za-z0-9\-]+)$"#

  static func isEmailAddress(_ value: String) -> Bool {
    value.count <= 254 && value.range(of: emailPattern, options: .regularExpression) != nil
  }

  /// The digits of a phone number written the ways people write them, or nil.
  static func phoneDigits(_ value: String) -> String? {
    let allowed = CharacterSet(charactersIn: "0123456789+-(). ")
    guard value.rangeOfCharacter(from: allowed.inverted) == nil,
      !value.dropFirst().contains("+")
    else { return nil }
    let digits = value.filter(\.isNumber)
    // Three digits covers short codes; fifteen is the E.164 maximum.
    guard (3...15).contains(digits.count) else { return nil }
    return value.hasPrefix("+") ? "+" + digits : digits
  }
}
