//
//  DesktopAutomationConversationRecordingActions.swift — drive the conversation detail's
//  "Recorded on" row without the cursor.
//
//  `list` reads the open conversation's event membership from the server. `show` / `hide` toggle
//  the recordings panel under the header's device stack. `open` and `separate` post the
//  notification the open detail observes, which calls the same handlers the panel's rows and its
//  confirmation call: a second caller of production code, never a second implementation of it.
//

import Foundation

extension DesktopAutomationActionRegistry {

  func registerConversationRecordingActions() {
    register(
      name: "conversation_detail_recording",
      summary: "List, show/hide, open, or separate the recordings of the open conversation's event",
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
      guard ["show", "hide"].contains(action) || (["open", "separate"].contains(action) && !recordingId.isEmpty)
      else {
        return ["error": "action must be list, show, hide, open, or separate; open and separate need recordingId"]
      }
      NotificationCenter.default.post(
        name: .desktopAutomationConversationRecordingRequested, object: nil,
        userInfo: ["conversationId": openId, "recordingId": recordingId, "action": action])
      return ["posted": "true", "conversation_id": openId, "recording_id": recordingId, "action": action]
    }
  }
}
