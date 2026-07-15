import Foundation

/// Immutable process-local projection of server-owned workflow control.
/// The cohort shell samples this before resolving Main Chat; no local data or
/// preference may reconstruct it, and absence means capability-off.
struct ChatFirstCapabilityProjection: Equatable, Sendable {
  let chatFirstUi: Bool
  let controlGeneration: Int

  init?(control: OmiAPI.TaskWorkflowControl) {
    guard control.chatFirstUi == true,
      control.workflowMode == .read,
      let generation = control.accountGeneration,
      generation >= 0
    else { return nil }
    chatFirstUi = true
    controlGeneration = generation
  }

  var dictionary: [String: Any] {
    ["chatFirstUi": chatFirstUi, "controlGeneration": controlGeneration]
  }
}
