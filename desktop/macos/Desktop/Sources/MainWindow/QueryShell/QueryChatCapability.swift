//
//  QueryChatCapability.swift — what Home's chat can *do*, as values rather than branches in a body.
//
//  Home is the app's only chat destination. The standalone chat page was deleted in `6be26e85bc`
//  because it was an unreachable reduced copy of this one (INV-NAV-1) — but it was carrying four
//  controls nothing else offered, and deleting the page deleted the controls. Clear, copy and the
//  jump to AI settings have had no home since. They belong here, on the one surface, and not on a
//  second destination.
//
//  Everything in this file is arithmetic or copy. No view, no provider, no window — so "the menu
//  offers Clear only when there is something to clear" is a test rather than a screenshot.
//
//  INV-6: nothing here owns a transcript. Each decision is computed *from* the one `ChatProvider`
//  and each action is performed *on* it.
//
//  Brand: nothing here picks a colour (INV-UI-1).
//

import Foundation

/// The answer panel's overflow menu, resolved from transcript state.
///
/// Two entries are conditional and one is not: the AI-settings jump is always available because it
/// is about how chat is configured, not about what is currently in it — a settings door that
/// disappears when the transcript is empty is a door you cannot find on a fresh install, which is
/// exactly when you need it.
struct HomeChatMenu: Equatable, Sendable {
  /// Put the whole conversation on the pasteboard. Pointless with nothing in it.
  let canCopy: Bool
  /// Clear the conversation. Deliberately unavailable mid-turn: clearing under a live send races
  /// the turn that is about to append to the thing being cleared.
  let canClear: Bool
  /// Whether the menu should be drawn at all. An overflow button that opens onto one permanently
  /// enabled item is chrome pretending to be a control.
  var isPresentable: Bool { canCopy || canClear }

  static func resolve(messageCount: Int, isSending: Bool, isClearing: Bool) -> HomeChatMenu {
    HomeChatMenu(
      canCopy: messageCount > 0 && !isClearing,
      canClear: messageCount > 0 && !isSending && !isClearing
    )
  }
}

/// The conversation as plain text, for the pasteboard.
enum HomeChatTranscript {
  /// `copyableText` rather than `text`, so an assistant turn contributes its answer and not its
  /// reasoning or its tool traffic — the same promise the per-message copy button already makes.
  /// A turn with nothing copyable (a pure tool row, a failed send) contributes no line at all
  /// instead of an attributed blank.
  static func plainText(_ messages: [ChatMessage], assistantName: String = "omi") -> String {
    messages
      .compactMap { message -> String? in
        let body = message.copyableText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty else { return nil }
        let speaker = message.sender == .user ? "You" : assistantName
        return "\(speaker): \(body)"
      }
      .joined(separator: "\n\n")
  }
}
