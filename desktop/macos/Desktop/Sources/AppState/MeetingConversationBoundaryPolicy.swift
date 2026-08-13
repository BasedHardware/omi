import Foundation

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
}
