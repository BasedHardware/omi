import Foundation

/// Whether capture may continue while the meeting gate has not yet answered.
///
/// Only Meetings is a *closed* gate that a detected call opens, so "we do not know yet" has to be
/// treated as "not in a call". Selecting Only Meetings from a live Always session builds a fresh
/// detector, so its first reconcile pass runs with `hasObservedState == false`; leaving capture
/// alone until the first probe lands would keep the microphone the previous mode opened running
/// after the user asked for it to be closed.
enum MeetingGateReadinessPolicy {
  static func shouldPauseCapture(
    mode: AssistantSettings.AudioRecordingMode, meetingStateReady: Bool
  ) -> Bool {
    mode == .onlyMeetings && !meetingStateReady
  }
}

enum MeetingConversationBoundaryPolicy {
  typealias Role = TranscriptionConversationRole

  struct Transition: Equatable, Sendable {
    let nextRole: Role
    let finalizationReason: TranscriptionFinalizationReason
  }

  /// Meeting observation is independent from capture gating. A detected edge
  /// rotates the logical conversation even when the microphone remains live in
  /// Always mode; stable detector samples never rotate twice.
  static func transition(previousRole: Role, meetingActive: Bool) -> Transition? {
    switch (previousRole, meetingActive) {
    case (.ambient, true):
      return Transition(nextRole: .meeting, finalizationReason: .meetingStarted)
    case (.meeting, false):
      return Transition(nextRole: .ambient, finalizationReason: .meetingEnded)
    case (.ambient, false), (.meeting, true):
      return nil
    }
  }

  static func committedRole(previousRole: Role, transition: Transition, rotationSucceeded: Bool) -> Role {
    rotationSucceeded ? transition.nextRole : previousRole
  }

  static func shouldFinishConversation(
    mode: AssistantSettings.AudioRecordingMode,
    meetingStateReady: Bool,
    shouldCapture: Bool,
    segmentCount: Int,
    hasSpeakerSegments: Bool
  ) -> Bool {
    mode == .onlyMeetings
      && meetingStateReady
      && !shouldCapture
      && (segmentCount > 0 || hasSpeakerSegments)
  }
}
