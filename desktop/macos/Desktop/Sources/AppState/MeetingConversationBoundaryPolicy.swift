import Foundation

enum MeetingConversationBoundaryPolicy {
  static func shouldFinishConversation(
    mode: AssistantSettings.SystemAudioCaptureMode,
    shouldCapture: Bool,
    segmentCount: Int,
    hasSpeakerSegments: Bool
  ) -> Bool {
    mode == .onlyDuringMeetings
      && !shouldCapture
      && (segmentCount > 0 || hasSpeakerSegments)
  }
}
