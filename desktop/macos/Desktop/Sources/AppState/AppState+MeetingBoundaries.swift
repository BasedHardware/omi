import Foundation

extension AppState {
  /// Serializes detector edges with session rotation. A second edge that lands
  /// while local STT tails are flushing replaces the pending level; after the
  /// current rotation completes we converge to the newest observed state.
  func handleMeetingObservation(active: Bool) async {
    guard isTranscribing else { return }
    if meetingBoundaryInProgress {
      pendingMeetingState = active
      return
    }
    guard
      let transition = MeetingConversationBoundaryPolicy.transition(
        previousRole: currentConversationRole,
        meetingActive: active)
    else { return }

    meetingBoundaryInProgress = true
    log("Transcription: meeting boundary — role=\(transition.nextRole.rawValue)")
    let result = await finishConversation(
      finalizationReason: transition.finalizationReason,
      allowEmptyRotation: true,
      nextConversationRole: transition.nextRole)
    let rotationSucceeded: Bool
    if case .error(let message) = result {
      rotationSucceeded = false
      log("Transcription: meeting boundary rotation failed — \(message)")
      currentConversationRole = MeetingConversationBoundaryPolicy.committedRole(
        previousRole: currentConversationRole,
        transition: transition,
        rotationSucceeded: false)
      meetingBoundaryInProgress = false
      pendingMeetingState = nil
      _ = stopTranscription()
      return
    } else {
      rotationSucceeded = true
    }
    currentConversationRole = MeetingConversationBoundaryPolicy.committedRole(
      previousRole: currentConversationRole,
      transition: transition,
      rotationSucceeded: rotationSucceeded)
    meetingBoundaryInProgress = false

    if let pending = pendingMeetingState {
      pendingMeetingState = nil
      await handleMeetingObservation(active: pending)
    }
  }
}
