import AppKit
import Foundation

/// What actually happened when the user asked to send a person their page.
enum PersonProfileShareOutcome: Equatable, Sendable {
  /// The native Messages composer opened, pre-addressed and pre-filled. The user still sends.
  case composerOpened
  /// The document was written and revealed in Finder (the fallback when we cannot address it).
  case revealedInFinder
  /// The text was placed on the pasteboard.
  case copied
  /// Nothing could be handed off; the payload is a user-facing reason.
  case unavailable(String)
}

/// Hands a rendered person profile to the user's own Messages composer.
///
/// **Omi never sends on the user's behalf.** The whole contract of this type is: render →
/// write a file → open the native composer prefilled → *the human presses Send*. It mirrors
/// the shipped mobile behaviour (`share_to_contacts_sheet.dart` opens the SMS composer rather
/// than sending) and Granola's "draft, don't send" follow-ups.
///
/// It also never drives Messages through an agent or AppleScript: `NSSharingService` is a
/// first-class AppKit API, which is exactly the "code owns the contract, agents only drive
/// what code cannot reach" rule in INV-INT-1. The app is not sandboxed
/// (`com.apple.security.app-sandbox` is `false` in `Omi.entitlements` /
/// `Omi-Release.entitlements`), and share services need no entitlement of their own, so this
/// adds no new entitlement and no new TCC prompt.
@MainActor
enum PersonProfileShare {

  /// Opens the Messages composer with `recipients` pre-addressed and `fileURL` attached.
  ///
  /// Returns `.unavailable(reason)` — never a crash — when there is no recipient, no file, or
  /// no compose-message share service on this Mac. Callers fall back to `revealInFinder`.
  static func compose(fileURL: URL, recipients: [String], body: String) -> PersonProfileShareOutcome {
    let addresses =
      recipients
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    guard !addresses.isEmpty else {
      return .unavailable("No phone number or email on file for this person.")
    }
    guard FileManager.default.fileExists(atPath: fileURL.path) else {
      return .unavailable("The profile document is no longer on disk.")
    }
    guard let service = NSSharingService(named: .composeMessage) else {
      return .unavailable("Messages isn’t available on this Mac.")
    }

    var items: [Any] = []
    let trimmedBody = body.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmedBody.isEmpty { items.append(trimmedBody) }
    items.append(fileURL)

    service.recipients = addresses
    guard service.canPerform(withItems: items) else {
      return .unavailable("Messages can’t attach this document right now.")
    }
    service.perform(withItems: items)
    return .composerOpened
  }

  /// Fallback path: show the written document in Finder so the user can send it themselves.
  static func revealInFinder(_ url: URL) -> PersonProfileShareOutcome {
    guard FileManager.default.fileExists(atPath: url.path) else {
      return .unavailable("The profile document is no longer on disk.")
    }
    NSWorkspace.shared.activateFileViewerSelecting([url])
    return .revealedInFinder
  }

  /// Last-resort path: put the profile on the pasteboard so it can be pasted anywhere.
  /// The markdown is third-party personal data — it goes to the pasteboard and nowhere else,
  /// and is never logged.
  static func copyMarkdown(_ markdown: String) -> PersonProfileShareOutcome {
    guard !markdown.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return .unavailable("There is nothing to copy yet.")
    }
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    guard pasteboard.setString(markdown, forType: .string) else {
      return .unavailable("Couldn’t write to the clipboard.")
    }
    return .copied
  }
}
