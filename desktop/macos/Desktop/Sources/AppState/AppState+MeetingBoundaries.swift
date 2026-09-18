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
  func ensureMeetingDetector(for mode: AssistantSettings.AudioRecordingMode) {
    if meetingDetector != nil, meetingDetectorMode != mode {
      meetingDetector?.stop()
      meetingDetector = nil
      meetingDetectorMode = nil
    }
    guard meetingDetector == nil, audioSource == .microphone else { return }

    let meetingProbe: @Sendable () -> Bool = {
      if #available(macOS 14.4, *) {
        if ConferencingApps.callAppIsUsingMicrophone() { return true }
        // On modern macOS, browser titles are only a capture-gating fallback;
        // Always mode keeps the stronger CoreAudio mic signal authoritative.
        return mode == .onlyMeetings && ConferencingApps.browserCallWindowPresent()
      }
      // macOS 14.0-14.3 has no CoreAudio process-input API. Keep the browser
      // title signal for Always and meetings-only capture, but never construct
      // meeting provenance while system-audio capture is disabled.
      return mode != .off && ConferencingApps.browserCallWindowPresent()
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
          if active, SystemCalendarMeetingContextFeature.isEnabled {
            // Permission and calendar I/O live outside the detector/audio path. This early sync
            // normally stores the invite before the eventual conversation finalization begins.
            Task(priority: .utility) {
              await SystemCalendarMeetingContextService.shared.prepareAroundNow()
            }
          }
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
    // The detector can report its initial state while the async SQLite session
    // owner is still being created. Do not rotate an unowned buffer: retain the
    // edge and replay it as soon as the session task installs currentSessionId.
    guard currentSessionId != nil else {
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
