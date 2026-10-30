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

  func deferMeetingRelaunchStart(
    source: AudioSource?, conversationRole: TranscriptionConversationRole,
    userInitiated: Bool, armedRetry: Bool, launchContext: CaptureLaunchContext.Kind?
  ) -> Bool {
    // Resolve the first automatic session's role before constructing either STT transport.
    // A crash may have ended the prior row, but must not create a confirmation-sized ambient row.
    if !userInitiated, !armedRetry, !CaptureLaunchContext.hasStartedCapture,
      conversationRole == .ambient, (source ?? audioSource) == .microphone, !meetingRelaunchChecked
    {
      let generation = recordingGeneration
      let requestedMode = AssistantSettings.shared.audioRecordingMode
      if meetingRelaunchCheckGeneration == generation, meetingRelaunchCheckMode == requestedMode { return true }
      meetingRelaunchCheckGeneration = generation
      meetingRelaunchCheckMode = requestedMode
      Task { @MainActor [weak self] in
        guard let self else { return }
        let role: TranscriptionConversationRole
        do {
          role = try await DeadlinedOperation.run(seconds: 3) {
            await self.meetingRelaunchRole(mode: requestedMode)
          }
        } catch {
          // Optional continuity evidence must not leave capture intent waiting on local I/O.
          role = .ambient
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "state_authority", from: "meeting_resume", to: "meeting_confirmation",
            reason: "timeout", outcome: .degraded)
        }
        // A stop or mode change may have queued a newer startup while lookup was suspended.
        guard self.meetingRelaunchCheckGeneration == generation,
          self.meetingRelaunchCheckMode == requestedMode
        else { return }
        self.meetingRelaunchCheckGeneration = nil
        self.meetingRelaunchCheckMode = nil
        guard self.recordingGeneration == generation, !self.isTranscribing,
          AssistantSettings.shared.audioRecordingMode == requestedMode
        else { return }
        self.meetingRelaunchChecked = true
        self.startTranscription(
          source: source, conversationRole: role, userInitiated: false, launchContext: launchContext)
      }
      return true
    }
    return false
  }

  /// The fallback capture-owner finalizer obeys the same resume hold as detector boundaries.
  func finalizeEndedMeetingIfNeeded(
    mode: AssistantSettings.AudioRecordingMode, meetingStateReady: Bool, shouldCapture: Bool
  ) {
    if !meetingEndFinalizationInProgress,
      !meetingBoundaryInProgress,
      MeetingConversationBoundaryPolicy.shouldFinishConversation(
        mode: mode,
        meetingStateReady: meetingStateReady,
        shouldCapture: shouldCapture,
        segmentCount: totalSegmentCount, conversationRole: currentConversationRole,
        hasSpeakerSegments: !speakerSegments.isEmpty,
        meetingResumePending: meetingDetector?.isMeetingConfirmed == true
      )
    {
      meetingEndFinalizationInProgress = true
      log("Transcription: Meeting ended — finishing conversation and waiting for the next meeting")
      Task { @MainActor in
        defer { self.meetingEndFinalizationInProgress = false }
        // A boundary rotation owns the same finalize — skip rather than run a
        // second `finishConversation` into the rotation serializer.
        guard !self.meetingBoundaryInProgress,
          MeetingConversationBoundaryPolicy.shouldFinishConversation(
            mode: self.audioRecordingMode,
            meetingStateReady: self.meetingDetector?.hasObservedState == true,
            shouldCapture: self.meetingDetector?.isMeetingActive == true,
            segmentCount: self.totalSegmentCount, conversationRole: self.currentConversationRole,
            hasSpeakerSegments: !self.speakerSegments.isEmpty,
            meetingResumePending: self.meetingDetector?.isMeetingConfirmed == true
          )
        else {
          log("Transcription: skipped meeting-ended finalization because meeting state changed")
          return
        }
        _ = await self.finishConversation(
          finalizationReason: .meetingEnded, finishedAt: self.meetingDetector?.lastMeetingEndedAt)
      }
    }
  }

  /// Calendar evidence is local and authorized; the strict on-edge audio rule still applies.
  /// This runs before any STT session or websocket is created, so both paths start as meeting.
  func meetingRelaunchRole(mode: AssistantSettings.AudioRecordingMode) async -> TranscriptionConversationRole {
    guard
      let end = try? await TranscriptionStorage.shared.interruptedMeetingEnd(
        before: CaptureLaunchContext.launchedAt, now: Date())
    else { return .ambient }
    let events = await SystemCalendarMeetingContextService.shared.activeEventIDs(covering: end)
    guard !events.isEmpty else { return .ambient }
    let apiAvailable: Bool
    if #available(macOS 14.4, *) { apiAvailable = true } else { apiAvailable = false }
    let shot = await Task.detached(priority: .utility) {
      ConferencingApps.captureCallAudioSnapshot(
        browserTitles: CallAudioBrowserTitlePolicy.capture(mode: mode, processInputAPIAvailable: apiAvailable))
    }.value
    return MeetingSessionResumePolicy.relaunchRole(
      hasInterruptedMeeting: true, activeCalendarEventIDs: events,
      callDetected: MeetingCallObservation.isDetected(
        snapshot: shot, mode: mode, processInputAPIAvailable: apiAvailable))
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
      calendarEventIDs: { await SystemCalendarMeetingContextService.shared.activeEventIDs() },
      onInitialStateObserved: { [weak self] in
        Task { @MainActor in
          guard let self, let detector = self.meetingDetector else { return }
          if let active = MeetingConversationBoundaryPolicy.initialObservation(
            captureActive: detector.isMeetingActive, meetingConfirmed: detector.isMeetingConfirmed)
          {
            await self.handleMeetingObservation(active: active)
          }
          await self.reconcileCapture()
        }
      },
      onCallChanged: { [weak self] in
        // A new call is a meeting start for context purposes too.
        Self.noteMeetingContext(active: true)
        Task { @MainActor in await self?.handleMeetingObservation(active: true) }
      },
      onChange: { [weak self] _ in
        Task { @MainActor in
          guard let self else { return }
          // Capture closes immediately; the confirmed conversation owns its resume window.
          await self.reconcileCapture()
        }
      },
      onConfirmedChange: { [weak self] active in
        Self.noteMeetingContext(active: active)
        let endedAt = active ? nil : self?.meetingDetector?.lastMeetingEndedAt
        Task { @MainActor in await self?.handleMeetingObservation(active: active, endedAt: endedAt) }
      },
      onNoteTakingNoticeReady: { [weak self] in
        guard let self, self.isTranscribing, self.currentConversationRole == .meeting else { return }
        MeetingNoteTakingNotice.present()
      }
    )
    meetingDetector = detector
    meetingDetectorMode = mode
    detector.start()
  }

  /// Context side work for a meeting starting or ending: the early calendar-invite sync and the
  /// context-subject event.
  private static func noteMeetingContext(active: Bool) {
    if active {
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
  func handleMeetingObservation(active: Bool, endedAt: Date? = nil) async {
    guard isTranscribing else { return }
    let endedAt = active ? nil : (endedAt ?? pendingMeetingEndedAt ?? meetingDetector?.lastMeetingEndedAt)
    if meetingBoundaryInProgress {
      pendingMeetingState = active
      pendingMeetingEndedAt = endedAt
      return
    }
    // The detector can report its initial state while the async SQLite session
    // owner is still being created. Do not rotate an unowned buffer: retain the
    // edge and replay it as soon as the session task installs currentSessionId.
    guard currentSessionId != nil else {
      pendingMeetingState = active
      pendingMeetingEndedAt = endedAt
      return
    }
    pendingMeetingEndedAt = nil
    let callChanged = active && meetingDetector?.hasPendingCallChange == true
    guard
      let transition = MeetingConversationBoundaryPolicy.transition(
        previousRole: currentConversationRole,
        meetingActive: active,
        callChanged: callChanged)
    else { return }

    reportMeetingBoundaryEvidence(active: active, callChanged: callChanged)

    // Starting a meeting already opens a fresh conversation for whichever call is on.
    if active { meetingDetector?.clearPendingCallChange() }
    meetingBoundaryInProgress = true
    log("Transcription: meeting boundary — role=\(transition.nextRole.rawValue)\(callChanged ? " (call changed)" : "")")
    let result = await finishConversation(
      finalizationReason: transition.finalizationReason,
      allowEmptyRotation: true,
      nextConversationRole: transition.nextRole,
      finishedAt: MeetingSessionResumePolicy.finalizationTime(mode: audioRecordingMode, offAt: endedAt))
    if case .busy = result {
      // A non-edge rotation (deferred .meetingEnded, BLE finish, Rewind finish)
      // holds the serializer. The edge stays pending — the in-flight rotation's
      // session-creation task replays `pendingMeetingState` when it installs the
      // new session id, so nothing is lost.
      pendingMeetingState = active
      pendingMeetingEndedAt = endedAt
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
      meetingDetector?.requestNoteTakingNotice()
    }

    if let pending = pendingMeetingState {
      pendingMeetingState = nil
      let pendingEnd = pendingMeetingEndedAt
      pendingMeetingEndedAt = nil
      await handleMeetingObservation(active: pending, endedAt: pendingEnd)
    }
  }
}
