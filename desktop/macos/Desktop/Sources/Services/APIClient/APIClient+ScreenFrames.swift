import Foundation

// MARK: - Screen-frame egress (meeting-note screenshots)
//
// Three of the six routes in `CONTRACT.md` §1 — the ones the desktop client calls. Sharing
// (`PATCH .../screenshot-sharing`, `GET .../shared/screenshots`) is web's surface, not this
// one's, so it is not here.

extension APIClient {
  /// `GET /v1/screen-frame-egress/settings`. The account-level gate for meeting-note screenshots
  /// (contract §6) — authoritative across every device, unlike the local `UserDefaults` mirror
  /// `MeetingNoteScreenshotsFeature.isEnabled` reads synchronously.
  func getScreenFrameSettings() async throws -> ScreenFrameSettingsWire {
    try await get("v1/screen-frame-egress/settings")
  }

  /// `PATCH /v1/screen-frame-egress/settings`.
  func updateScreenFrameSettings(enabled: Bool) async throws -> ScreenFrameSettingsWire {
    struct UpdateRequest: Encodable {
      let meetingNoteScreenshotsEnabled: Bool
      enum CodingKeys: String, CodingKey {
        case meetingNoteScreenshotsEnabled = "meeting_note_screenshots_enabled"
      }
    }
    return try await patch(
      "v1/screen-frame-egress/settings",
      body: UpdateRequest(meetingNoteScreenshotsEnabled: enabled))
  }

  /// `POST /v1/screen-frame-egress/adjudications`. Uploads canonical candidate bytes and gets
  /// back the conversation's whole frame set — never a verdict, never an approval (contract §0).
  func adjudicateScreenFrames(
    _ request: ScreenFrameAdjudicationRequestWire
  ) async throws -> ScreenFrameAdjudicationResponseWire {
    try await post("v1/screen-frame-egress/adjudications", body: request)
  }

  /// `GET /v1/conversations/{id}/screenshots`. The source of truth for what a note currently
  /// shows — used both for the initial render and to recover from an expired signed URL.
  func getConversationScreenFrames(conversationID: String) async throws -> ConversationScreenFrameSet {
    try await get("v1/conversations/\(conversationID)/screenshots")
  }

  /// `DELETE /v1/conversations/{id}/screenshots/{frameID}`. Void by design, matching every other
  /// delete on this client (`deleteConversation`, `deleteGoal`, …) — the server may promote
  /// another frame to banner when this one was it, but that is not expressed in a delete
  /// response here. Callers re-fetch with `getConversationScreenFrames` afterward.
  func deleteConversationScreenFrame(conversationID: String, frameID: String) async throws {
    try await delete("v1/conversations/\(conversationID)/screenshots/\(frameID)")
  }
}
