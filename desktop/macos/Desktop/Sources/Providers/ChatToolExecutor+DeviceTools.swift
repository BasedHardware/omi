import Foundation

/// Executors for the on-device tool surface: Contacts lookup, Messages reads,
/// Messages sending, and AppleScript actuation.
///
/// Every executor returns JSON with an `ok` flag plus a `reason` code on
/// failure. When the failure is a missing macOS permission the payload also
/// carries `next_tool` so the agent asks for that one permission instead of
/// guessing, matching the shape `permissionRequiredMessage` already uses.
extension ChatToolExecutor {

  /// Tools whose arguments are the user's private content rather than a
  /// description of the request.
  ///
  /// `send_message` carries the recipient and the exact message body;
  /// `run_applescript` carries the whole script. Both are reachable in release
  /// builds, so logging the raw arguments wrote private message text to the
  /// production log on ordinary use. These log their shape instead — enough to
  /// debug a malformed call, nothing anyone would mind keeping.
  private static let sensitiveArgumentTools: Set<String> = [
    "send_message", "run_applescript", "read_message_history", "list_mail_messages", "search_contacts",
  ]

  static func redactedArgumentSummary(for toolCall: ToolCall) -> String {
    guard sensitiveArgumentTools.contains(toolCall.name) else { return "\(toolCall.arguments)" }
    let shape = toolCall.arguments.keys.sorted().map { key -> String in
      guard let value = toolCall.arguments[key] else { return "\(key)=<null>" }
      if let text = value as? String { return "\(key)=<\(text.count) chars>" }
      return "\(key)=<\(type(of: value))>"
    }
    return "[redacted: \(shape.joined(separator: ", "))]"
  }

  /// Full Disk Access status with the restart case spelled out.
  ///
  /// `not_granted` is the wrong thing to tell the model when the user has
  /// already granted the permission — it sends them back to System Settings to
  /// toggle something that is already on. The grant only takes effect for a
  /// process started after it, so the fix is to relaunch.
  nonisolated static func fullDiskAccessStatus() -> String {
    switch FullDiskAccessProbe.currentState() {
    case .granted: return "granted"
    case .grantedPendingRestart: return "granted_pending_restart"
    case .denied: return "not_granted"
    }
  }

  nonisolated static func deviceToolJSON(_ payload: [String: Any]) -> String {
    guard
      let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
      let json = String(data: data, encoding: .utf8)
    else { return "\(payload)" }
    return json
  }

  nonisolated static func deviceToolFailure(
    reason: String,
    message: String,
    requiredPermission: String? = nil
  ) -> String {
    var payload: [String: Any] = ["ok": false, "reason": reason, "error": message]
    if let requiredPermission {
      payload["permission"] = requiredPermission
      payload["next_tool"] = "request_permission"
      payload["next_tool_arguments"] = ["type": requiredPermission]
    }
    return deviceToolJSON(payload)
  }

  /// Reads an integer argument, treating anything unusable as absent.
  ///
  /// The tool schemas declare `type: number` with no bounds, so `1e100` and
  /// `NaN` are both protocol-legal. `Int(_: Double)` traps on either, which
  /// would take the whole app down on a model typo — the range check is what
  /// keeps a bad argument a validation matter rather than a crash.
  private static func boundedInt(_ args: [String: Any], _ key: String, default fallback: Int) -> Int {
    if let value = args[key] as? Int { return value }
    if let value = args[key] as? Double {
      guard value.isFinite,
        value >= Double(Int.min), value <= Double(Int.max)
      else { return fallback }
      return Int(value)
    }
    if let value = args[key] as? String, let parsed = Int(value) { return parsed }
    return fallback
  }

  /// Runs a blocking child-process call off the main actor.
  ///
  /// `ChatToolExecutor` is `@MainActor`, so `osascript` and Messages sends were
  /// running on the UI thread and holding it for as long as the timeout allowed
  /// — up to two minutes. That froze the whole desktop, including the
  /// cancellation and account-transition controls the user would reach for to
  /// stop it. The owner checks stay at the physical-effect boundary; only the
  /// waiting moves.
  private static func offMainActor<T: Sendable>(
    _ work: @escaping @Sendable (@escaping @Sendable () -> Bool) throws -> T
  ) async throws -> T {
    try await Task.detached(priority: .userInitiated) {
      try work { Task.isCancelled }
    }.value
  }

  /// Reads a chat identifier, accepting the JSON shapes a model actually emits.
  ///
  /// A quoted `"12345"` used to fall through to nil and silently become a handle
  /// lookup or a missing-reference error, reading a different conversation than
  /// the one asked for.
  private static func chatIdentifier(_ args: [String: Any]) -> Int64? {
    if let value = args["chat_id"] as? Int64 { return value }
    if let value = args["chat_id"] as? Int { return Int64(value) }
    if let value = args["chat_id"] as? Double {
      guard value.isFinite, value.rounded() == value, value >= Double(Int64.min), value <= Double(Int64.max) else {
        return nil
      }
      return Int64(value)
    }
    if let value = args["chat_id"] as? String {
      return Int64(value.trimmingCharacters(in: .whitespacesAndNewlines))
    }
    return nil
  }

  private static func iso8601(_ date: Date?) -> String? {
    guard let date else { return nil }
    return ISO8601DateFormatter().string(from: date)
  }

  // MARK: - Contacts

  static func executeSearchContacts(_ args: [String: Any]) async -> String {
    guard let query = (args["query"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
      !query.isEmpty
    else {
      return deviceToolFailure(reason: "missing_query", message: "Provide a name to search for.")
    }
    let limit = boundedInt(args, "limit", default: 10)

    // A first-use prompt is the normal path here; only a hard denial is a failure.
    // The TCC callback may arrive long after the tool is cancelled or the owner
    // changes, so the prompt rides the same once-guard adapter as the other
    // permission waits — cancellation resumes it instead of leaving owner-bound
    // work suspended behind an unanswered prompt.
    if ContactsReaderService.authorizationStatus() == .notDetermined {
      _ = await awaitCancellablePermissionRequest { completion in
        Task {
          completion(await ContactsReaderService.requestAccess())
        }
      }
    }

    do {
      let contacts = try ContactsReaderService.search(query: query, limit: limit)
      return deviceToolJSON([
        "ok": true,
        "query": query,
        "count": contacts.count,
        "contacts": contacts.map { contact in
          [
            "id": contact.id,
            "name": contact.displayName,
            "organization": contact.organization,
            "phone_numbers": contact.phoneNumbers.map { ["label": $0.label, "value": $0.value] },
            "email_addresses": contact.emailAddresses.map { ["label": $0.label, "value": $0.value] },
            "preferred_messaging_handle": contact.preferredMessagingHandle ?? "",
          ] as [String: Any]
        },
      ])
    } catch let error as ContactsReaderError {
      return deviceToolFailure(
        reason: error.reasonCode,
        message: error.errorDescription ?? "Contacts lookup failed.",
        requiredPermission: error.requiredPermission)
    } catch {
      return deviceToolFailure(reason: "lookup_failed", message: error.localizedDescription)
    }
  }

  // MARK: - Messages reads

  static func executeListMessageChats(_ args: [String: Any]) async -> String {
    let limit = boundedInt(args, "limit", default: 20)
    do {
      let chats = try await MessagesReaderService.shared.listChats(limit: limit)
      return deviceToolJSON([
        "ok": true,
        "count": chats.count,
        "chats": chats.map { chat in
          [
            "chat_id": chat.id,
            "display_name": chat.displayName,
            "handles": chat.handles,
            "service": chat.service,
            "last_message_at": iso8601(chat.lastMessageAt) ?? "",
            "last_message_preview": chat.lastMessagePreview,
          ] as [String: Any]
        },
      ])
    } catch let error as MessagesReaderError {
      return deviceToolFailure(
        reason: error.reasonCode,
        message: error.errorDescription ?? "Could not read the Messages database.",
        requiredPermission: error.requiredPermission)
    } catch {
      return deviceToolFailure(reason: "store_read_failed", message: error.localizedDescription)
    }
  }

  static func executeReadMessageHistory(_ args: [String: Any]) async -> String {
    let chatID = chatIdentifier(args)
    let handle = (args["handle"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
    guard chatID != nil || (handle?.isEmpty == false) else {
      return deviceToolFailure(
        reason: "missing_chat_reference",
        message: "Provide chat_id from list_message_chats, or a handle.")
    }
    let limit = boundedInt(args, "limit", default: 30)

    do {
      let messages = try await MessagesReaderService.shared.readHistory(
        chatID: chatID, handle: handle, limit: limit)
      return deviceToolJSON([
        "ok": true,
        "count": messages.count,
        "messages": messages.map { message in
          [
            "message_id": message.id,
            "chat_id": message.chatID,
            "handle": message.handle,
            "text": message.text,
            "is_from_me": message.isFromMe,
            "sent_at": iso8601(message.sentAt) ?? "",
            "service": message.service,
            "attachment_count": message.attachmentCount,
          ] as [String: Any]
        },
      ])
    } catch let error as MessagesReaderError {
      return deviceToolFailure(
        reason: error.reasonCode,
        message: error.errorDescription ?? "Could not read the conversation.",
        requiredPermission: error.requiredPermission)
    } catch {
      return deviceToolFailure(reason: "store_read_failed", message: error.localizedDescription)
    }
  }

  // MARK: - Mail reads

  static func executeListMailMessages(_ args: [String: Any]) async -> String {
    let limit = boundedInt(args, "limit", default: 30)
    do {
      let messages = try await AppleMailReaderService.shared.readRecentMessages(limit: limit)
      return deviceToolJSON([
        "ok": true,
        "count": messages.count,
        // Headers only. Bodies live in .emlx files this reader never opens, and
        // the tool description tells the model to say so rather than invent one.
        "messages": messages.map { message in
          [
            "message_id": message.id,
            "subject": message.subject,
            "sender_address": message.senderAddress,
            "sender_name": message.senderName,
            "received_at": iso8601(message.receivedAt) ?? "",
            "is_read": message.isRead,
            "is_flagged": message.isFlagged,
            "was_answered": message.wasAnswered,
          ] as [String: Any]
        },
      ])
    } catch let error as AppleMailReaderError {
      return deviceToolFailure(
        reason: error.reasonCode,
        message: error.errorDescription ?? "Could not read the Apple Mail index.",
        requiredPermission: error.requiredPermission)
    } catch {
      return deviceToolFailure(reason: "store_read_failed", message: error.localizedDescription)
    }
  }

  // MARK: - Messages send

  static func executeSendMessage(_ args: [String: Any]) async -> String {
    guard let to = (args["to"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
      !to.isEmpty
    else {
      return deviceToolFailure(reason: "empty_recipient", message: "Provide a recipient handle.")
    }
    guard let text = args["text"] as? String,
      !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return deviceToolFailure(reason: "empty_body", message: "Provide the message text to send.")
    }
    let service = MessageSendService(rawValueOrAuto: args["service"] as? String)
    let filePath = (args["file_path"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)

    log("Executing send_message to a resolved handle via \(service.rawValue)")

    do {
      let (attempt, confirmation) = try await MessageSendConfirmer.sendThenConfirm(handle: to, text: text) {
        try await sendAttempt {
          try await offMainActor {
            try MessagesSenderService.send(
              to: to,
              text: text,
              service: service,
              filePath: filePath,
              cancellationCheck: $0)
          }
        }
      }
      log(
        "send_message outcome=\(confirmation.status.rawValue)"
          + " reason=\(confirmation.unconfirmedReason?.rawValue ?? "none")"
          + " timed_out=\(attempt == .timedOut) after_error=\(confirmation.succeededAfterError)"
          + " checks=\(confirmation.checks) waited_ms=\(confirmation.waitedMilliseconds)")
      let outcome: MessageSendOutcome
      switch attempt {
      case .completed(let completed): outcome = completed
      case .timedOut: outcome = timedOutSendOutcome(handle: to, confirmation: confirmation)
      }
      return sendMessageResult(
        outcome, confirmation: confirmation, sendTimedOut: attempt == .timedOut, charactersSent: text.count)
    } catch {
      return sendMessageFailure(error)
    }
  }

  /// What a timed-out send can honestly report: only what the history shows,
  /// the service of the row that confirmed it (empty when nothing did). Whether
  /// an attachment went too is unknown, so none is reported.
  nonisolated static func timedOutSendOutcome(
    handle: String, confirmation: MessageSendConfirmation
  ) -> MessageSendOutcome {
    MessageSendOutcome(handle: handle, service: confirmation.confirmedService ?? "", attachedFile: nil)
  }

  /// The `send_message` result when no send completed. A stop that arrived
  /// before Messages was asked reads as `cancelled` with nothing sent, never as
  /// a failed send or raw error text.
  nonisolated static func sendMessageFailure(_ error: Error) -> String {
    switch error {
    case is CancellationError:
      return deviceToolJSON([
        "ok": false,
        "status": "cancelled",
        "reason": "cancelled",
        "error": "The send was stopped before Messages was asked to send it. Nothing was sent.",
      ])
    case let error as AppleScriptRunnerError:
      return deviceToolFailure(
        reason: error.reasonCode,
        message: error.errorDescription ?? "Messages automation was refused.",
        requiredPermission: error.requiredPermission)
    case let error as MessagesSenderError:
      return deviceToolFailure(
        reason: error.reasonCode,
        message: error.errorDescription ?? "Could not send the message.")
    default:
      return deviceToolFailure(reason: "send_failed", message: "Messages could not send the message.")
    }
  }

  /// How Omi's one send attempt ended, before the history check.
  enum SendAttempt: Sendable, Equatable {
    case completed(MessageSendOutcome)
    /// Messages did not answer within the time limit; it may still have sent.
    case timedOut
  }

  /// Runs Omi's one send. A timeout becomes `.timedOut` instead of an error:
  /// Messages may still have sent the message, and the history check says
  /// what happened, which is more use than "may or may not have been sent".
  nonisolated static func sendAttempt(
    _ send: @Sendable () async throws -> MessageSendOutcome
  ) async throws -> SendAttempt {
    do {
      return .completed(try await send())
    } catch MessagesSenderError.sendTimedOut {
      return .timedOut
    }
  }

  /// The `send_message` result, with the outcome in plain words for the model.
  ///
  /// Only `not_delivered` is a failure. `unconfirmed` is an unknown outcome:
  /// `outcome_unknown` makes the kernel ledger record it that way rather than
  /// as a success, and the summary asks for a check in Messages because a
  /// second send could duplicate it.
  nonisolated static func sendMessageResult(
    _ outcome: MessageSendOutcome, confirmation: MessageSendConfirmation, sendTimedOut: Bool = false,
    charactersSent: Int
  ) -> String {
    var summary: String
    switch confirmation.status {
    case .delivered:
      summary = "Sent and delivered: Messages marked this message as delivered."
    case .sent:
      summary =
        "Sent, not yet delivered: Messages recorded this message as sent, but had not marked it delivered when Omi stopped checking. The recipient's device may be offline. Do not send it again."
    case .notDelivered:
      summary =
        "Not delivered: Messages marked this message with an error. Omi did not send it again. Tell the person, and send it again only if they ask."
    case .unconfirmed:
      let why: String
      switch confirmation.unconfirmedReason {
      case .historyUnreadable: why = "Omi could not read the Messages history"
      case .ambiguous: why = "more than one identical message appeared at the same moment"
      case .ambiguousRecipient: why = "the number matches more than one conversation in Messages"
      case .notYetSent: why = "Messages had not yet marked it as sent"
      case .checkStopped: why = "the check was stopped"
      case .noMatchingRow, nil: why = "the message did not appear in the Messages history in time"
      }
      summary =
        "Unconfirmed: Omi asked Messages to send this, but could not confirm it (\(why)). It may or may not have been sent. Do not send it again; ask the person to check Messages first."
    }
    if confirmation.succeededAfterError {
      summary +=
        " Messages recorded an error on one attempt first, and the message then went through on another, for example as a text message."
    }
    if sendTimedOut {
      summary = "Messages did not answer in time, so Omi checked the Messages history. " + summary
    }

    var payload: [String: Any] = [
      "ok": confirmation.status != .notDelivered,
      "status": confirmation.status.rawValue,
      "summary": summary,
      "to": outcome.handle,
      "service": outcome.service,
      "attached_file": outcome.attachedFile ?? "",
      "characters_sent": charactersSent,
    ]
    if let reason = confirmation.unconfirmedReason {
      payload["unconfirmed_reason"] = reason.rawValue
    }
    if confirmation.status == .unconfirmed {
      payload["outcome_unknown"] = true
    }
    if confirmation.status == .notDelivered {
      payload["reason"] = "not_delivered"
    }
    if confirmation.succeededAfterError {
      payload["succeeded_after_error"] = true
    }
    if sendTimedOut {
      payload["send_timed_out"] = true
    }
    return deviceToolJSON(payload)
  }

  // MARK: - AppleScript

  static func executeRunAppleScript(_ args: [String: Any]) async -> String {
    guard let script = args["script"] as? String,
      !script.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return deviceToolFailure(reason: "empty_script", message: "Provide an AppleScript to run.")
    }
    let timeout = TimeInterval(boundedInt(args, "timeout_seconds", default: 30))

    do {
      let result = try await offMainActor {
        try AppleScriptRunner.run(script: script, timeoutSeconds: timeout, cancellationCheck: $0)
      }
      if result.timedOut {
        return deviceToolFailure(
          reason: "timed_out",
          message:
            "The script did not finish within \(Int(timeout))s. It may still be running; check the target app before retrying."
        )
      }
      if !result.succeeded {
        return deviceToolFailure(
          reason: "execution_failed",
          message: result.errorOutput.isEmpty
            ? "osascript exited with status \(result.exitCode)." : result.errorOutput)
      }
      return deviceToolJSON([
        "ok": true,
        "output": result.output,
        "exit_code": Int(result.exitCode),
      ])
    } catch let error as AppleScriptRunnerError {
      return deviceToolFailure(
        reason: error.reasonCode,
        message: error.errorDescription ?? "AppleScript failed.",
        requiredPermission: error.requiredPermission)
    } catch {
      return deviceToolFailure(reason: "execution_failed", message: error.localizedDescription)
    }
  }
}
