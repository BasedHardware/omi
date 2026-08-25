import Foundation

enum MeetingConversationBoundaryPolicy {
  static func shouldFinishConversation(
    mode: AssistantSettings.SystemAudioCaptureMode,
    meetingStateReady: Bool,
    shouldCapture: Bool,
    segmentCount: Int,
    hasSpeakerSegments: Bool
  ) -> Bool {
    mode == .onlyDuringMeetings
      && meetingStateReady
      && !shouldCapture
      && (segmentCount > 0 || hasSpeakerSegments)
  }
}
