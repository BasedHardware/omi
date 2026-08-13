import Foundation

extension AppState {
  func automationObserveMeetingBoundary(active: Bool) -> String {
    guard AppBuild.isNonProduction, automationCaptureTestSessionActive else { return "unavailable" }
    guard
      let transition = MeetingConversationBoundaryPolicy.transition(
        previousRole: currentConversationRole,
        meetingActive: active
      )
    else { return currentConversationRole.rawValue }
    currentConversationRole = transition.nextRole
    return currentConversationRole.rawValue
  }

  /// Keeps the probe's evidence policy aligned with settings changes during a recording.
  func ensureMeetingDetector(for mode: AssistantSettings.SystemAudioCaptureMode) {
    if meetingDetector != nil, meetingDetectorMode != mode {
      meetingDetector?.stop()
      meetingDetector = nil
      meetingDetectorMode = nil
    }
    guard meetingDetector == nil, audioSource == .microphone else { return }

    let meetingProbe: @Sendable () -> Bool = {
      if #available(macOS 14.4, *), ConferencingApps.callAppIsUsingMicrophone() { return true }
      // Browser titles are useful for an explicit meetings-only capture gate,
      // but too weak to mint notes-ready boundaries in Always mode.
      return mode == .onlyDuringMeetings && ConferencingApps.browserCallWindowPresent()
    }
    let detector = MeetingDetector(
      isMeetingNow: meetingProbe,
      onInitialStateObserved: { [weak self] in
        Task { @MainActor in
          guard let self, let active = self.meetingDetector?.isMeetingActive else { return }
          await self.handleMeetingObservation(active: active)
          await self.reconcileCapture()
        }
      },
      onChange: { [weak self] active in
        Task { @MainActor in
          await self?.handleMeetingObservation(active: active)
          await self?.reconcileCapture()
        }
        if let event = TaskLocalContextEvent.normalized(
          kind: .meeting,
          rawReference: active ? "meeting-active" : "meeting-ended"
        ) {
          Task { await ContextSubjectBindingService.shared.resolveAndObserve(event) }
        }
      }
    )
    meetingDetector = detector
    meetingDetectorMode = mode
    detector.start()
  }

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
