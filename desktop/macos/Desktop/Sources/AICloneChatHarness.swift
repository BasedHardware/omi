import Foundation

/// Shared mailbox between the automation bridge and the AI Clone chat sheet: the live tab
/// publishes a state snapshot here so harness actions can verify the real UI without
/// accessibility access or cursor input. Only readable through the local bridge, which is
/// enabled on non-production bundles only.
@MainActor
final class AICloneChatAutomation {
  static let shared = AICloneChatAutomation()
  /// Latest state published by the open live chat tab; nil when no chat sheet is open.
  var liveSnapshot: [String: String]?
  /// The contact whose chat sheet is currently presented (authoritative, owned by
  /// `AIClonePage`). The live tab's poll loop and notification handlers gate on this so a
  /// dismissed-but-cached sheet view (macOS keeps sheet hosts around for reuse) can never
  /// keep polling or react to triggers.
  var activeContactId: String?
}

/// Headless automation actions for the AI Clone chat sheet (live conversation + practice).
/// They post the same notifications / read the same state as the real controls, so they
/// exercise the genuine UI code paths.
///
/// Actions:
///   ai_clone_open_chat contact_id=…  — navigate to AI Clone and open the chat sheet
///   ai_clone_chat_state              — dump the live tab's state (transcript, suggestion)
///   ai_clone_chat_suggest            — trigger "Suggest reply" in the open live tab
///   ai_clone_chat_close              — close the chat sheet
enum AICloneChatHarness {

  @MainActor
  static func register(on registry: DesktopAutomationActionRegistry) {
    registry.register(
      name: "ai_clone_open_chat",
      summary: "Open the AI Clone chat sheet (live conversation) for a trained contact",
      params: ["contact_id"]
    ) { params in
      guard let contactId = params["contact_id"], !contactId.isEmpty else {
        return ["error": "missing 'contact_id'"]
      }
      // Same route as omi-ctl navigate, but without activating the app so verification
      // never steals the user's focus or Space.
      NotificationCenter.default.post(
        name: .desktopAutomationNavigateRequested, object: nil,
        userInfo: ["target": "ai_clone"])
      NotificationCenter.default.post(
        name: .aiCloneOpenChatRequested, object: nil, userInfo: ["contactId": contactId])
      return [
        "requested": contactId,
        "note": "sheet opens once the page has loaded; poll ai_clone_chat_state",
      ]
    }

    registry.register(
      name: "ai_clone_chat_state",
      summary: "Dump the open AI Clone live chat tab's state (transcript tail + suggestion)"
    ) { _ in
      AICloneChatAutomation.shared.liveSnapshot ?? ["open": "false"]
    }

    registry.register(
      name: "ai_clone_chat_suggest",
      summary: "Trigger 'Suggest reply' in the open AI Clone live chat tab"
    ) { _ in
      guard AICloneChatAutomation.shared.liveSnapshot != nil else {
        return ["error": "no chat sheet open — run ai_clone_open_chat first"]
      }
      NotificationCenter.default.post(name: .aiCloneChatSuggestRequested, object: nil)
      return ["requested": "true", "note": "generation is async; poll ai_clone_chat_state"]
    }

    registry.register(
      name: "ai_clone_chat_close",
      summary: "Close the AI Clone chat sheet"
    ) { _ in
      NotificationCenter.default.post(name: .aiCloneCloseChatRequested, object: nil)
      return nil
    }
  }
}
