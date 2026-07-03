import Foundation

enum IMessageSenderError: LocalizedError {
  case scriptUnavailable
  case sendFailed(String)

  var errorDescription: String? {
    switch self {
    case .scriptUnavailable:
      return "Couldn't build the Messages script."
    case .sendFailed(let message):
      return message
    }
  }
}

/// Sends an approved reply through Messages.app via AppleScript.
///
/// Targets the exact thread by its chat GUID (the durable path across macOS
/// versions; `buddy` targeting is flaky). Only ever called after the user taps
/// Send (or for opted-in auto-reply). The AppleScript is executed on a dedicated
/// background queue via an async boundary so delivering the Apple event — which can
/// block on TCC automation prompts or slow chat resolution — never freezes the UI.
enum IMessageSenderService {

  private static let executionQueue = DispatchQueue(label: "com.omi.imessage.sender")

  static func send(text: String, toChatGUID chatGUID: String) async throws {
    let escapedText =
      text
      .replacingOccurrences(of: "\\", with: "\\\\")
      .replacingOccurrences(of: "\"", with: "\\\"")
      .replacingOccurrences(of: "\n", with: "\" & linefeed & \"")
    let escapedGUID = chatGUID.replacingOccurrences(of: "\"", with: "\\\"")

    let source = """
      tell application "Messages"
        set targetChat to a reference to chat id "\(escapedGUID)"
        send "\(escapedText)" to targetChat
      end tell
      """

    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
      executionQueue.async {
        guard let script = NSAppleScript(source: source) else {
          continuation.resume(throwing: IMessageSenderError.scriptUnavailable)
          return
        }
        var errorDict: NSDictionary?
        script.executeAndReturnError(&errorDict)
        if let errorDict {
          let message =
            (errorDict[NSAppleScript.errorMessage] as? String)
            ?? "Messages couldn't send this reply. Open Messages and try manually."
          continuation.resume(throwing: IMessageSenderError.sendFailed(message))
        } else {
          continuation.resume()
        }
      }
    }
  }
}
