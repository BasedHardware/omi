import ApplicationServices
import Foundation

/// AppleScript, for the things clicking cannot do well.
///
/// A click is how you use an app; a script is how you ask it a question. Reading
/// the selected messages in Mail, the current tab's URL in Safari, or the name of
/// every open document is one line of AppleScript and a dozen screenshots
/// otherwise — and the answer is exact rather than read off a picture.
///
/// **Run out of process, on purpose.** The obvious implementation is
/// `NSAppleScript` in-process, which the app already uses for its own automation
/// probe. It cannot be used for a script a model wrote: `NSAppleScript` has no
/// timeout, and an AppleScript that opens a dialog, targets a hung app, or simply
/// loops blocks its thread forever. In-process that thread is the main one, so a
/// bad script freezes Omi's whole UI — including the button and the hotkey that
/// stop computer control, which is exactly when the user reaches for them. A
/// child process can be killed.
///
/// TCC attribution survives the split: `osascript` is spawned by Omi and not
/// re-parented, so macOS holds Omi responsible and the Automation prompt names
/// Omi, not a helper the user has never heard of.
enum CuaAppleScript {
  struct Result {
    let output: String
    let failure: String?
  }

  /// Wall clock a script gets. Long enough for Mail to answer about a large
  /// mailbox, short enough that a wedged script is a failed tool call rather
  /// than a hung session.
  static let defaultTimeout: TimeInterval = 20

  /// Whether Omi may already script `bundleID`, without prompting.
  ///
  /// Apple Events are granted per target, so there is no process-wide answer:
  /// permission to drive Finder says nothing about Safari. `askUserIfNeeded:
  /// false` makes this a read — the prompt belongs to the call the user actually
  /// asked for, not to a status check.
  static func isPermitted(bundleID: String) -> Bool {
    var target = AEAddressDesc()
    let identifier = Array(bundleID.utf8)
    let status = identifier.withUnsafeBufferPointer { buffer in
      AECreateDesc(
        AEKeyword(typeApplicationBundleID), buffer.baseAddress, buffer.count, &target)
    }
    guard status == noErr else { return false }
    defer { AEDisposeDesc(&target) }
    return AEDeterminePermissionToAutomateTarget(
      &target, AEEventClass(typeWildCard), AEEventID(typeWildCard), false) == noErr
  }

  /// Run a script and return what it printed.
  ///
  /// The script is written to a file and passed by path rather than as an
  /// argument, so a newline or a quote in it cannot become a second argument.
  static func run(_ source: String, timeout: TimeInterval = defaultTimeout) -> Result {
    let scriptURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-cua-\(UUID().uuidString).applescript")
    defer { try? FileManager.default.removeItem(at: scriptURL) }
    do {
      try Data(source.utf8).write(to: scriptURL, options: .atomic)
    } catch {
      return Result(output: "", failure: "Could not stage the script: \(error.localizedDescription)")
    }

    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
    process.arguments = [scriptURL.path]
    let out = Pipe()
    let err = Pipe()
    process.standardOutput = out
    process.standardError = err

    do {
      try process.run()
    } catch {
      return Result(output: "", failure: "Could not run osascript: \(error.localizedDescription)")
    }

    // Read both pipes while the process runs. A script that writes more than a
    // pipe buffer holds before exiting would otherwise deadlock against a
    // `waitUntilExit` that never returns.
    let outData = readInBackground(out)
    let errData = readInBackground(err)

    let deadline = Date().addingTimeInterval(timeout)
    while process.isRunning, Date() < deadline {
      Thread.sleep(forTimeInterval: 0.02)
    }
    if process.isRunning {
      process.terminate()
      // SIGTERM is a request; a script blocked in a dialog ignores it.
      Thread.sleep(forTimeInterval: 0.2)
      if process.isRunning { kill(process.processIdentifier, SIGKILL) }
      return Result(
        output: "",
        failure:
          "The script did not finish within \(Int(timeout))s and was stopped. A script that drives another app waits here when Automation has not been approved for it — check System Settings ▸ Privacy & Security ▸ Automation — and a script that opens a dialog waits for a click that no one is there to make."
      )
    }

    let output = String(decoding: outData.value, as: UTF8.self)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let errorText = String(decoding: errData.value, as: UTF8.self)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if process.terminationStatus != 0 {
      return Result(output: output, failure: errorText.isEmpty ? "osascript failed" : errorText)
    }
    return Result(output: output, failure: nil)
  }

  private static func readInBackground(_ pipe: Pipe) -> Box {
    let box = Box()
    DispatchQueue.global(qos: .userInitiated).async {
      box.value = pipe.fileHandleForReading.readDataToEndOfFile()
    }
    return box
  }

  /// A mailbox for one pipe's bytes, filled by the reader and read after the
  /// process has exited.
  final class Box: @unchecked Sendable {
    private let lock = NSLock()
    private var storage = Data()

    var value: Data {
      get {
        lock.lock()
        defer { lock.unlock() }
        return storage
      }
      set {
        lock.lock()
        storage = newValue
        lock.unlock()
      }
    }
  }
}
