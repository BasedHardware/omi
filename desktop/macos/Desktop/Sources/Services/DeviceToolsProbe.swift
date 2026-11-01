import Foundation

/// Hermetic probe for the on-device tool surface, driven by the automation
/// bridge action `device_tools_probe`.
///
/// Every branch is deterministic on any machine and on CI: a deliberately
/// absent Messages store, a send rejected on validation before Messages.app is
/// contacted, and an AppleScript that only echoes its own argv. None of it
/// requires Full Disk Access, Automation, or Contacts to be granted, and none
/// of it touches the user's real message history or delivers a message.
enum DeviceToolsProbe {
  /// Used when the caller names no store. It must not exist, so the read
  /// classifies identically whether or not this Mac has Messages signed in.
  static let absentStorePath = "/nonexistent/omi-e2e-messages-fixture.db"

  /// Contains AppleScript syntax that would execute if untrusted values were
  /// interpolated into script source instead of passed as argv.
  static let injectionMarker = "\" & (do shell script \"echo pwned\") & \""

  static func run(messagesDbPath: String?) async -> [String: String] {
    var detail: [String: String] = [:]

    let storePath = messagesDbPath.flatMap { $0.isEmpty ? nil : $0 } ?? absentStorePath
    do {
      let chats = try await MessagesReaderService.shared.listChats(
        limit: 5, storeOverride: URL(fileURLWithPath: storePath))
      detail["messagesRead"] = "true"
      detail["messagesChatCount"] = "\(chats.count)"
    } catch let error as MessagesReaderError {
      detail["messagesRead"] = "false"
      detail["messagesClassification"] = error.reasonCode
      detail["messagesRequiredPermission"] = error.requiredPermission ?? ""
    } catch {
      detail["messagesRead"] = "false"
      detail["messagesClassification"] = "unexpected_error"
    }

    // Same deliberately-absent-store treatment as the Messages read above, so
    // the Mail classification is exercised without a real mailbox or FDA.
    do {
      let mail = try await AppleMailReaderService.shared.readRecentMessages(
        limit: 5, storeOverride: URL(fileURLWithPath: absentStorePath))
      detail["mailRead"] = "true"
      detail["mailMessageCount"] = "\(mail.count)"
    } catch let error as AppleMailReaderError {
      detail["mailRead"] = "false"
      detail["mailClassification"] = error.reasonCode
      detail["mailRequiredPermission"] = error.requiredPermission ?? ""
    } catch {
      detail["mailRead"] = "false"
      detail["mailClassification"] = "unexpected_error"
    }

    do {
      _ = try MessagesSenderService.send(
        to: "+10000000000", text: "   ", service: .imessage, filePath: nil)
      detail["sendValidation"] = "not_rejected"
    } catch let error as MessagesSenderError {
      detail["sendValidation"] = error.reasonCode
    } catch {
      detail["sendValidation"] = "unexpected_error"
    }

    do {
      let result = try AppleScriptRunner.run(
        script: "on run argv\nreturn item 1 of argv\nend run",
        arguments: [injectionMarker],
        timeoutSeconds: 10)
      detail["appleScriptOk"] = "\(result.succeeded)"
      detail["appleScriptEchoedArgv"] = "\(result.output == injectionMarker)"
    } catch let error as AppleScriptRunnerError {
      detail["appleScriptOk"] = "false"
      detail["appleScriptClassification"] = error.reasonCode
    } catch {
      detail["appleScriptOk"] = "false"
      detail["appleScriptClassification"] = "unexpected_error"
    }

    // Status read only — an automated run must never raise a permission prompt.
    detail["contactsStatus"] = await MainActor.run { ChatToolExecutor.contactsPermissionStatus() }

    detail["ok"] = "true"
    return detail
  }
}
