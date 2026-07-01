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
/// Send — nothing is auto-sent. Runs on the main actor because Apple events
/// prefer the main run loop.
enum IMessageSenderService {

  @MainActor
  static func send(text: String, toChatGUID chatGUID: String) throws {
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

    guard let script = NSAppleScript(source: source) else {
      throw IMessageSenderError.scriptUnavailable
    }

    var errorDict: NSDictionary?
    script.executeAndReturnError(&errorDict)
    if let errorDict {
      let message =
        (errorDict[NSAppleScript.errorMessage] as? String)
        ?? "Messages couldn't send this reply. Open Messages and try manually."
      throw IMessageSenderError.sendFailed(message)
    }
  }
}
