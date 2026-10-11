import Foundation

/// Sends iMessage/SMS through Messages.app.
///
/// The recipient handle, body, and attachment path are passed as `argv` rather
/// than interpolated into the script — a message body is attacker-influenced
/// text (it can come from a conversation the agent just read) and must never
/// reach the AppleScript compiler as source.
enum MessageSendService: String, Sendable {
  case auto
  case imessage
  case sms

  init(rawValueOrAuto raw: String?) {
    switch raw?.lowercased() {
    case "imessage": self = .imessage
    case "sms": self = .sms
    default: self = .auto
    }
  }

  /// AppleScript service-type constants, in the order this mode should try them.
  var serviceTypes: [String] {
    switch self {
    case .imessage: return ["iMessage"]
    case .sms: return ["SMS"]
    case .auto: return ["iMessage", "SMS"]
    }
  }
}

struct MessageSendOutcome: Sendable {
  let handle: String
  let service: String
  let attachedFile: String?
}

enum MessagesSenderError: LocalizedError {
  case emptyRecipient
  case emptyBody
  case attachmentNotFound(path: String)
  case allServicesFailed(detail: String)
  case partiallySent(service: String, detail: String)

  var errorDescription: String? {
    switch self {
    case .emptyRecipient: return "No recipient handle was provided."
    case .emptyBody: return "Refusing to send an empty message."
    case .attachmentNotFound(let path): return "Attachment not found at \(path)."
    case .allServicesFailed(let detail):
      return "Messages.app could not send to that recipient: \(detail)"
    case .partiallySent(let service, let detail):
      return
        "The message text was sent over \(service) but the attachment was not: \(detail). The recipient has already received the text — do not resend it. Ask whether they still want the file."
    }
  }

  var reasonCode: String {
    switch self {
    case .emptyRecipient: return "empty_recipient"
    case .emptyBody: return "empty_body"
    case .attachmentNotFound: return "attachment_not_found"
    case .allServicesFailed: return "send_failed"
    case .partiallySent: return "partially_sent"
    }
  }
}

enum MessagesSenderService {
  /// Reported by the script when the body went out but the attachment did not.
  static let partialSendMarker = "omi_partial:"

  /// `argv` order: handle, body, attachment path ("" when absent).
  ///
  /// The body and the attachment are two separate effects. If the body is
  /// delivered and the attachment is then rejected — an unreadable path, a
  /// directory, an unsupported type — an uncaught error would abort the script
  /// with a non-zero exit, and `auto` would move on to SMS and deliver the body
  /// a second time. The attachment failure is therefore caught and reported as a
  /// partial send, so the caller can stop instead of retrying.
  private static func sendScript(serviceType: String) -> String {
    """
    on run argv
      set targetHandle to item 1 of argv
      set messageBody to item 2 of argv
      set attachmentPath to item 3 of argv
      set bodySent to false
      tell application "Messages"
        set targetAccount to 1st account whose service type = \(serviceType)
        set targetParticipant to participant targetHandle of targetAccount
        if messageBody is not "" then
          send messageBody to targetParticipant
          set bodySent to true
        end if
        if attachmentPath is not "" then
          try
            send (POSIX file attachmentPath) to targetParticipant
          on error attachmentError
            if bodySent then
              return "\(partialSendMarker)" & attachmentError
            end if
            error attachmentError
          end try
        end if
      end tell
      return "sent"
    end run
    """
  }

  static func send(
    to handle: String,
    text: String,
    service: MessageSendService,
    filePath: String?,
    timeoutSeconds: TimeInterval = 30,
    cancellationCheck: @escaping @Sendable () -> Bool = { false }
  ) throws -> MessageSendOutcome {
    let trimmedHandle = handle.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmedHandle.isEmpty else { throw MessagesSenderError.emptyRecipient }
    guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      throw MessagesSenderError.emptyBody
    }

    var attachment = ""
    if let filePath, !filePath.isEmpty {
      guard FileManager.default.fileExists(atPath: filePath) else {
        throw MessagesSenderError.attachmentNotFound(path: filePath)
      }
      attachment = filePath
    }

    var failures: [String] = []
    for serviceType in service.serviceTypes {
      do {
        let result = try AppleScriptRunner.run(
          script: sendScript(serviceType: serviceType),
          arguments: [trimmedHandle, text, attachment],
          timeoutSeconds: timeoutSeconds,
          cancellationCheck: cancellationCheck)
        if result.succeeded {
          // The body reached the recipient but the attachment did not. Retrying
          // on another service would send the body twice, so this stops here and
          // says plainly what did and did not happen.
          if result.output.hasPrefix(Self.partialSendMarker) {
            let detail = String(result.output.dropFirst(Self.partialSendMarker.count))
            throw MessagesSenderError.partiallySent(service: serviceType, detail: detail)
          }
          return MessageSendOutcome(
            handle: trimmedHandle,
            service: serviceType,
            attachedFile: attachment.isEmpty ? nil : attachment)
        }
        // A timeout is not a clean failure: Messages may still deliver, so stop
        // rather than retrying on another service and double-sending.
        if result.timedOut {
          throw MessagesSenderError.allServicesFailed(
            detail:
              "Messages.app did not respond within \(Int(timeoutSeconds))s; the message may or may not have been sent. Do not retry without checking the thread."
          )
        }
        failures.append("\(serviceType): \(result.errorOutput)")
      } catch let error as AppleScriptRunnerError {
        // A TCC denial applies to Messages.app as a whole; another service type
        // will hit the same wall.
        throw error
      }
    }

    throw MessagesSenderError.allServicesFailed(detail: failures.joined(separator: "; "))
  }
}
