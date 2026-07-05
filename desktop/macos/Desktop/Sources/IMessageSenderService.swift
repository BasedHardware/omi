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

/// Thread-safe cancellation flag shared between the task-cancellation handler (which
/// can fire on any thread) and the main-queue send block.
private final class SendCancellationBox: @unchecked Sendable {
  private let lock = NSLock()
  private var cancelled = false
  var isCancelled: Bool {
    lock.lock()
    defer { lock.unlock() }
    return cancelled
  }
  func cancel() {
    lock.lock()
    cancelled = true
    lock.unlock()
  }
}

/// Sends an approved reply through Messages.app via AppleScript.
///
/// Targets the exact thread by its chat GUID (the durable path across macOS
/// versions; `buddy` targeting is flaky). Only ever called after the user taps
/// Send (or for opted-in auto-reply).
///
/// `NSAppleScript` is documented as main-thread-only and is not thread-safe, so the
/// script is created and executed on the main queue. Dispatching it async keeps the
/// calling Task from blocking, which avoids the previous synchronous `@MainActor`
/// stall. Tradeoff (honest): the main run loop IS still blocked for the duration of
/// the Apple event — including any first-launch TCC automation prompt or slow chat
/// resolution — so a slow send can briefly hitch the UI. There is no safe way to run
/// `NSAppleScript` itself off the main thread; doing the work off-main would require
/// reworking this to `NSUserAppleScriptTask` or an XPC helper (see PR discussion).
enum IMessageSenderService {

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

    // Don't even enqueue if the task is already cancelled (e.g. auto-reply was
    // toggled off while the draft was being generated).
    try Task.checkCancellation()

    let box = SendCancellationBox()
    try await withTaskCancellationHandler {
      try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
        DispatchQueue.main.async {
          // Cancelled between enqueue and execution — don't send (sends are irreversible).
          if box.isCancelled {
            continuation.resume(throwing: CancellationError())
            return
          }
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
    } onCancel: {
      box.cancel()
    }
  }
}
