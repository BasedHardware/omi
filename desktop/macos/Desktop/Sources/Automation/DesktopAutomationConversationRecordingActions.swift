//
//  DesktopAutomationConversationRecordingActions.swift — drive the conversation detail's
//  "Recorded on" row without the cursor.
//
//  `list` reads the open conversation's event membership from the server. `show` / `hide` toggle
//  the recordings panel under the header's device stack. `open` and `separate` post the
//  notification the open detail observes, which calls the same handlers the panel's rows and its
//  confirmation call: a second caller of production code, never a second implementation of it.
//  `request_separate` raises the confirmation itself (what a row's Separate… does) without
//  confirming it.
//

import Foundation

extension DesktopAutomationActionRegistry {

  func registerConversationRecordingActions() {
    register(
      name: "conversations_discarded",
      effects: [.localState, .networkOrModel],
      summary: "Show/hide discarded conversations using the list filter, or read its current scope",
      params: ["enabled"]
    ) { params in
      guard AppBuild.isNonProduction, let appState = AppState.current else {
        return ["error": "requires a non-production main window"]
      }
      if let enabled = params["enabled"] {
        guard ["true", "false"].contains(enabled) else { return ["error": "enabled must be true or false"] }
        if appState.showDiscardedConversations != (enabled == "true") {
          await appState.toggleDiscardedConversations()
        }
      }
      return [
        "include_discarded": String(appState.showDiscardedConversations),
        "discarded_count": String(appState.conversations.filter(\.discarded).count),
        "visible_count": String(appState.conversations.count),
      ]
    }

    register(
      name: "conversation_detail_recording",
      effects: [.localState, .networkOrModel],
      summary:
        "List, show/hide, open, separate, or request_separate (raise the confirmation) the recordings of the open conversation's event",
      params: ["action", "recordingId"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "conversation_detail_recording is disabled on production bundles"]
      }
      guard let openId = ConversationDetailAutomationState.shared.openConversationId else {
        return ["error": "no open conversation"]
      }
      let action = params["action"] ?? "list"
      if action == "list" {
        let conversation = try await APIClient.shared.getConversation(id: openId)
        return [
          "conversation_id": openId,
          "capture_group_id": conversation.captureGroup?.id ?? "none",
          "member_ids": (conversation.captureGroup?.members.map(\.id) ?? []).joined(separator: ","),
        ]
      }
      let recordingId = params["recordingId"] ?? ""
      guard
        ["show", "hide"].contains(action)
          || (["open", "separate", "request_separate"].contains(action) && !recordingId.isEmpty)
      else {
        return [
          "error":
            "action must be list, show, hide, open, separate, or request_separate; all but list/show/hide need recordingId"
        ]
      }
      NotificationCenter.default.post(
        name: .desktopAutomationConversationRecordingRequested, object: nil,
        userInfo: ["conversationId": openId, "recordingId": recordingId, "action": action])
      return ["posted": "true", "conversation_id": openId, "recording_id": recordingId, "action": action]
    }

    register(
      name: "conversation_detail_prompt",
      effects: [.localState, .networkOrModel, .remoteWrite],
      summary:
        "Raise rename/delete, restore a discarded conversation, or press action item N's task control (add_task)",
      params: ["prompt", "index"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "conversation_detail_prompt is disabled on production bundles"]
      }
      guard let openId = ConversationDetailAutomationState.shared.openConversationId else {
        return ["error": "no open conversation"]
      }
      let prompt = params["prompt"] ?? ""
      guard ["rename", "delete", "add_task", "restore"].contains(prompt) else {
        return ["error": "prompt must be rename, delete, add_task, or restore"]
      }
      let index = Int(params["index"] ?? "0") ?? 0
      NotificationCenter.default.post(
        name: .desktopAutomationConversationPromptRequested, object: nil,
        userInfo: ["conversationId": openId, "prompt": prompt, "index": index])
      return ["posted": "true", "conversation_id": openId, "prompt": prompt, "index": "\(index)"]
    }
  }
}
