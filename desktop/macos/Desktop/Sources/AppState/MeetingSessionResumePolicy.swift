import Foundation

/// Shared startup admission: calendar overlap alone never turns ambient capture into a meeting.
enum MeetingSessionResumePolicy {
  /// Always mode keeps recording during evidence gaps; its captured tail must stay inside
  /// the stored interval. Only Meetings has a closed gate whose original off edge is exact.
  static func finalizationTime(mode: AssistantSettings.AudioRecordingMode, offAt: Date?) -> Date? {
    mode == .onlyMeetings ? offAt : nil
  }

  static func relaunchRole(
    hasInterruptedMeeting: Bool, activeCalendarEventIDs: Set<String>, callDetected: Bool
  ) -> TranscriptionConversationRole {
    hasInterruptedMeeting && !activeCalendarEventIDs.isEmpty && callDetected ? .meeting : .ambient
  }
}
