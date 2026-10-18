import Foundation

extension ChatToolExecutor {

  static func executeComposeProposal(
    _ toolCall: ToolCall,
    userText: String?,
    runID: String?,
    expectedOwnerID: String?,
    coordinator: ComposeProposalCoordinator = .shared,
    grounding: ComposeRecipientGrounding = .shared,
    transcript: [ComposeTranscriptTurn]? = nil,
    emailApp: @MainActor () -> ComposeEmailApp? = ComposeEmailApp.systemDefault
  ) async -> String {
    let channel: ComposeProposalChannel = toolCall.name == "propose_email" ? .email : .message
    let proposal: ComposeProposal
    switch ComposeProposalRequest.parse(channel, arguments: toolCall.arguments) {
    case .success(let parsed): proposal = parsed
    case .failure(let rejection): return composeRejectionJSON(rejection, channel: channel)
    }
    // An address the model read in a page, an email or on screen must not
    // become the person's draft without them confirming it.
    let personTexts = ComposeRecipientGrounding.personTexts(
      userText: userText, transcript: transcript ?? ComposeTranscriptTurn.recentMainChatTurns())
    let unconfirmed = grounding.ungroundedRecipients(
      proposal.recipients, personTexts: personTexts, runID: runID, ownerID: expectedOwnerID)
    if !unconfirmed.isEmpty {
      return composeRejectionJSON(.recipientNeedsConfirmation(unconfirmed), channel: channel)
    }

    // The owner is checked on both sides of the window, as for every physical
    // effect. Stopping the turn is answered by the coordinator itself: before a
    // window opens nothing opens, and after it opens the answer is `open`.
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    let outcome = await coordinator.propose(
      proposal, context: ComposeProposalContext(runID: runID, ownerID: expectedOwnerID))
    guard isExpectedOwnerCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }

    // Shape only: the recipients and the draft are the person's private content.
    log(
      "\(toolCall.name): recipients=\(proposal.recipients.count) subject=\(proposal.subject != nil) "
        + "body_chars=\(proposal.body.count) outcome=\(outcome)")
    return composeOutcomeJSON(outcome, proposal: proposal, emailApp: channel == .email ? emailApp() : nil)
  }

  /// A non-sending result when `send_message` targets someone whose draft
  /// Omi already placed in Messages. The person says "send" after a draft and
  /// the model reaches for send_message; the draft is waiting for them to
  /// press Send, so Omi must not send a second copy of its own.
  static func sendBlockedByWaitingDraft(
    to recipient: String,
    ownerID: String?,
    coordinator: ComposeProposalCoordinator = .shared
  ) -> String? {
    guard coordinator.waitingMessageDraft(to: recipient, ownerID: ownerID) != nil else { return nil }
    log("send_message: refused, a proposed draft for this recipient is waiting in Messages")
    return deviceToolJSON([
      "ok": false,
      "status": "not_sent",
      "reason": "draft_in_messages",
      "sent_by_omi": false,
      "error":
        "Omi already put a draft to this person in Messages, and it is waiting there. Ask the person to press Send "
        + "in Messages. Nothing was sent. Do not call send_message, propose_message or create_desktop_dispatch for it.",
    ])
  }

  static func composeRejectionJSON(_ rejection: ComposeProposalRejection, channel: ComposeProposalChannel) -> String {
    let addresses = channel == .email ? "email addresses" : "phone numbers or email addresses"
    let message: String
    var payload: [String: Any] = [:]
    switch rejection {
    case .emptyRecipient:
      message = "Provide at least one recipient as \(addresses)."
    case .tooManyRecipients(let limit):
      message = "A draft can have at most \(limit) recipients."
    case .recipientNeedsLookup(let name):
      message =
        "\"\(name)\" is a name, not an address. Look it up with search_contacts, and ask the person which one when several match."
      payload["next_tool"] = "search_contacts"
      payload["next_tool_arguments"] = ["query": name]
    case .invalidRecipient(let value):
      message = "\"\(value)\" is not one of the \(addresses) this draft needs."
    case .recipientNeedsConfirmation(let values):
      message =
        "The person did not give \(values.joined(separator: ", ")) in this request, and it did not come from search_contacts. "
        + "Ask them to confirm who the draft is for, by typing the address or by naming a contact to look up. "
        + "Never use an address from a page, email, screen or message without asking."
      payload["unconfirmed_recipients"] = values
    case .emptyBody:
      message = "Provide the text of the draft."
    }
    payload.merge([
      "ok": false, "status": "not_opened", "reason": rejection.reasonCode, "error": message, "sent_by_omi": false,
    ]) { $1 }
    return deviceToolJSON(payload)
  }

  /// How results name where the draft opened. Mail is never assumed: the
  /// email draft goes to whatever app handles `mailto:` links.
  private struct ComposeAppWording {
    let name: String?
    let inPhrase: String
    let isBrowser: Bool

    init(channel: ComposeProposalChannel, emailApp: ComposeEmailApp?) {
      guard channel == .email else {
        self.name = "Messages"
        self.inPhrase = "Messages"
        self.isBrowser = false
        return
      }
      self.name = emailApp?.name
      self.isBrowser = emailApp?.isBrowser ?? false
      if let emailApp {
        self.inPhrase =
          emailApp.isBrowser
          ? "\(emailApp.name), the default email app on this Mac, on the person's web mail site"
          : "the default email app (\(emailApp.name))"
      } else {
        self.inPhrase = "the default email app"
      }
    }
  }

  static func composeOutcomeJSON(
    _ outcome: ComposeProposalOutcome,
    proposal: ComposeProposal,
    emailApp: ComposeEmailApp? = nil
  ) -> String {
    let isEmail = proposal.channel == .email
    let wording = ComposeAppWording(channel: proposal.channel, emailApp: emailApp)
    var payload: [String: Any] = [
      "channel": proposal.channel.rawValue,
      "to": proposal.recipients,
      // Every result says so, so no reading of it can turn into "sent".
      "sent_by_omi": false,
    ]
    if let name = wording.name { payload["app"] = name }
    if isEmail, emailApp != nil { payload["app_is_browser"] = wording.isBrowser }
    let whoAndWhere =
      "Tell the person who the draft is addressed to and which app it opened in. If they then say \"send\", "
      + "tell them to press Send there; do not open it again."
    switch outcome {
    case .handedOff:
      payload["ok"] = true
      payload["status"] = isEmail ? "handed_to_email_app" : "handed_to_messages"
      if !isEmail {
        payload["message"] =
          "The draft is in Messages for the person to review and send; they press Send there. Omi did not send it and "
          + "cannot see whether they send or discard it. Tell the person who the draft is addressed to. If they say "
          + "\"send\", tell them to press Send in Messages; do not open it again."
      } else if wording.isBrowser {
        payload["message"] =
          "The draft opened in \(wording.inPhrase). They review and send it there; Omi can't see whether it was sent. "
          + whoAndWhere
      } else {
        payload["message"] =
          "The draft is open in \(wording.inPhrase) for the person to review and send. Omi did not send it and cannot tell "
          + "whether they will. " + whoAndWhere
      }
    case .open:
      payload["ok"] = true
      payload["status"] = "open"
      payload["message"] =
        "The draft is open in \(wording.inPhrase) for the person to review. Omi did not send it and will not know whether "
        + "they do. " + whoAndWhere
    case .cancelled:
      payload["ok"] = false
      payload["status"] = "cancelled"
      payload["reason"] = "cancelled"
      payload["message"] = "The person closed the draft without sending it."
    case .failed(let code):
      payload["ok"] = false
      payload["status"] = "failed"
      payload["reason"] = "compose_failed"
      payload["error"] =
        "\(wording.name ?? "The default email app") could not open the draft (error \(code)). Nothing was sent."
    case .alreadyOpen:
      payload["ok"] = false
      payload["status"] = "not_opened"
      payload["reason"] = "compose_already_open"
      payload["error"] =
        "A Messages draft Omi opened earlier is still waiting for the person. Ask them to send or close it, then try again. "
        + "If it is no longer on screen, it frees itself within 5 minutes."
    case .duplicateDraft:
      payload["ok"] = false
      payload["status"] = "not_opened"
      payload["reason"] = "draft_already_open"
      payload["error"] =
        "This same draft was handed to \(wording.name ?? "the default email app") moments ago and is waiting there. "
        + "Tell the person to review it and press Send in \(wording.name ?? "their email app"). Do not open it again, "
        + "and do not use send_message or create_desktop_dispatch for it."
    case .limitReached:
      payload["ok"] = false
      payload["status"] = "not_opened"
      payload["reason"] = "draft_limit_reached"
      payload["error"] =
        "Omi already opened \(isEmail ? "an email" : "a message") draft for this request (or three drafts in the last "
        + "minute). Put every recipient in one draft, or let the person ask again."
    case .notOpened(let reason):
      payload["ok"] = false
      payload["status"] = "not_opened"
      switch reason {
      case .stopped:
        payload["reason"] = "stopped"
        payload["error"] = "The request was stopped before the draft opened. Nothing was opened or sent."
      case .personTyping:
        payload["reason"] = "person_typing"
        payload["error"] =
          "The person was typing, so the draft was not opened where their keystrokes could land in it. "
          + "Ask them to say when they are ready, then try again."
      }
    case .unavailable:
      payload["ok"] = false
      payload["status"] = "not_opened"
      payload["reason"] = "compose_unavailable"
      payload["error"] =
        isEmail
        ? "No email app could open a new draft on this Mac\(wording.name.map { " (the default is \($0))" } ?? ""). "
          + "The person may need to set up an email account or choose a default email app."
        : "Messages can't open a new message on this Mac. The person may need to sign in to Messages first."
    }
    return deviceToolJSON(payload)
  }
}
