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
  /// Replacing the detector drops its call identities and any pending call change; the new
  /// detector adopts whatever call is on as the current one.
  func ensureMeetingDetector(for mode: AssistantSettings.AudioRecordingMode) {
    if meetingDetector != nil, meetingDetectorMode != mode {
      meetingDetector?.stop()
      meetingDetector = nil
      meetingDetectorMode = nil
    }
    guard meetingDetector == nil, audioSource == .microphone else { return }

    let detector = MeetingDetector(
      mode: mode,
      onInitialStateObserved: { [weak self] in
        Task { @MainActor in
          guard let self, let active = self.meetingDetector?.isMeetingActive else { return }
          await self.handleMeetingObservation(active: active)
          await self.reconcileCapture()
        }
      },
      onCallChanged: { [weak self] in
        // A new call is a meeting start for context purposes too.
        Self.noteMeetingContext(active: true)
        Task { @MainActor in await self?.handleMeetingObservation(active: true) }
      },
      onChange: { [weak self] active in
        Self.noteMeetingContext(active: active)
        Task { @MainActor in
          await self?.handleMeetingObservation(active: active)
          await self?.reconcileCapture()
        }
      }
    )
    meetingDetector = detector
    meetingDetectorMode = mode
    detector.start()
  }

  /// Context side work for a meeting starting or ending: the early calendar-invite sync and the
  /// context-subject event.
  private static func noteMeetingContext(active: Bool) {
    if active, SystemCalendarMeetingContextFeature.isEnabled {
      // Permission and calendar I/O live outside the detector/audio path. This early sync
      // normally stores the invite before the eventual conversation finalization begins.
      Task(priority: .utility) {
        await SystemCalendarMeetingContextService.shared.prepareAroundNow()
      }
    }
    if let event = TaskLocalContextEvent.normalized(
      kind: .meeting,
      rawReference: active ? "meeting-active" : "meeting-ended"
    ) {
      Task { await ContextSubjectBindingService.shared.resolveAndObserve(event) }
    }
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
    // The detector can report its initial state while the async SQLite session
    // owner is still being created. Do not rotate an unowned buffer: retain the
    // edge and replay it as soon as the session task installs currentSessionId.
    guard currentSessionId != nil else {
      pendingMeetingState = active
      return
    }
    let callChanged = active && meetingDetector?.hasPendingCallChange == true
    guard
      let transition = MeetingConversationBoundaryPolicy.transition(
        previousRole: currentConversationRole,
        meetingActive: active,
        callChanged: callChanged)
    else { return }

    // Starting a meeting already opens a fresh conversation for whichever call is on.
    if active { meetingDetector?.clearPendingCallChange() }
    meetingBoundaryInProgress = true
    log("Transcription: meeting boundary — role=\(transition.nextRole.rawValue)\(callChanged ? " (call changed)" : "")")
    let result = await finishConversation(
      finalizationReason: transition.finalizationReason,
      allowEmptyRotation: true,
      nextConversationRole: transition.nextRole)
    if case .busy = result {
      // A non-edge rotation (deferred .meetingEnded, BLE finish, Rewind finish)
      // holds the serializer. The edge stays pending — the in-flight rotation's
      // session-creation task replays `pendingMeetingState` when it installs the
      // new session id, so nothing is lost.
      pendingMeetingState = active
      if callChanged { meetingDetector?.restorePendingCallChange() }
      meetingBoundaryInProgress = false
      return
    }
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
      // A concurrent stop is the usual cause of a mid-rotation generation
      // change; it owns the terminal event — stopping again would double-emit
      // `Desktop Recording Stopped`. Only a still-live session gets torn down.
      if isTranscribing {
        captureAttempt?.noteErrorTerminal()
        _ = stopTranscription(finalizationReason: .rotationFailed)
      }
      return
    } else {
      rotationSucceeded = true
    }
    currentConversationRole = MeetingConversationBoundaryPolicy.committedRole(
      previousRole: currentConversationRole,
      transition: transition,
      rotationSucceeded: rotationSucceeded)
    meetingBoundaryInProgress = false

    if MeetingConversationBoundaryPolicy.shouldAnnounceNoteTaking(
      committedRole: currentConversationRole, rotationSucceeded: rotationSucceeded)
    {
      MeetingNoteTakingNotice.present()
    }

    if let pending = pendingMeetingState {
      pendingMeetingState = nil
      await handleMeetingObservation(active: pending)
    }
  }
}
