@preconcurrency import AVFoundation
import Combine
import SwiftUI
@preconcurrency import UserNotifications

/// Whether a cloud-published proactive message earns a desktop delivery.
///
/// Pure so the decision is testable without a runtime owner, a notification
/// service, or a live listen socket — the handler previously had no way to
/// assert "shown here, suppressed there", only that it did not crash.
///
/// This deliberately stops at *routing*. Once a message is admitted it goes to
/// `NotificationService`, which owns the master toggle, the frequency throttle,
/// the snooze and the presence withholding. Re-deciding any of those here would
/// give the cloud a second, divergent copy of the user's notification policy,
/// which is the exact failure this type exists to prevent.
enum ProactiveListenAdmission {
  enum Reason: String, Equatable {
    case emptyMessage
    case noRuntimeOwner
  }

  enum Outcome: Equatable {
    case deliver(title: String, message: String, assistantId: String)
    case skip(Reason)
  }

  static let fallbackAssistantID = "proactive-listen"

  static func decide(
    appID: String,
    title: String,
    message: String,
    hasRuntimeOwner: Bool
  ) -> Outcome {
    guard !message.isEmpty else { return .skip(.emptyMessage) }
    // A stale listen session must not deliver to whoever is signed in now.
    guard hasRuntimeOwner else { return .skip(.noRuntimeOwner) }
    return .deliver(
      title: title,
      message: message,
      assistantId: appID.isEmpty ? fallbackAssistantID : appID)
  }
}

@MainActor
extension AppState {
  func handleBackendSegments(
    _ segments: [TranscriptionService.BackendSegment],
    lane: LocalTranscriptionLane? = nil
  ) {
    var segmentsToPersist = [TranscriptionService.BackendSegment]()

    for segment in segments {
      guard !segment.text.isEmpty else { continue }

      // Extract speaker_id from backend (e.g. "SPEAKER_00" → 0)
      let speakerId = segment.speaker_id ?? 0

      // Barge-in interruption: if the user speaks while voice playback is active,
      // halt playback immediately so Omi never talks over the user.
      if VoiceBargeInPolicy.shouldInterrupt(
        isUser: segment.is_user,
        speaker: speakerId,
        text: segment.text,
        isSpeaking: FloatingBarVoicePlaybackService.shared.isSpeaking
      ) {
        log("Transcription [BARGE-IN]: User spoke mid-playback; interrupting voice output")
        FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
      }

      // Convert backend segment to local SpeakerSegment
      let translations = (segment.translations ?? []).map {
        SegmentTranslation(lang: $0.lang, text: $0.text)
      }
      if lane != nil, !segment.is_user, let personId = segment.person_id, liveSpeakerPersonMap[speakerId] != personId {
        liveSpeakerPersonMap[speakerId] = personId
      }
      let newSeg = SpeakerSegment(
        segmentId: segment.id,
        speaker: speakerId,
        text: segment.text,
        start: segment.start,
        end: segment.end,
        isUser: segment.is_user,
        personId: segment.person_id,
        translations: translations,
        lane: lane
      )

      // Upsert: if we already have a segment with this ID, update it; otherwise append
      if let segId = segment.id,
        let existingIdx = speakerSegments.firstIndex(where: { $0.segmentId == segId })
      {
        // Adjust word count: subtract old words, add new words
        let oldWords = speakerSegments[existingIdx].text.split(separator: " ").count
        totalWordCount += newSeg.text.split(separator: " ").count - oldWords
        // Preserve existing translations if the backend didn't send new ones
        var updatedSeg = newSeg
        if translations.isEmpty && !speakerSegments[existingIdx].translations.isEmpty {
          updatedSeg.translations = speakerSegments[existingIdx].translations
        }
        speakerSegments[existingIdx] = updatedSeg
        log(
          "Transcript [UPDATE] Speaker \(speakerId) [\(String(format: "%.1f", segment.start))s-\(String(format: "%.1f", segment.end))s]: \(segment.text.prefix(80))"
        )
        segmentsToPersist.append(segment)
      } else if sttSession.useLocalSTT {
        // Echo dedup is local-STT-only by architecture: only the local engine
        // runs the two capture lanes (mic + system-audio tap) that produce
        // cross-lane playback duplicates. Cloud mode mixes mic and system into
        // one mono stream, so the same playback cannot transcribe twice and
        // is_user comes from backend diarization — running this dedup there
        // would risk suppressing real speech with no echo to remove.
        switch LocalTranscriptionDuplicatePolicy.decision(for: newSeg, existing: speakerSegments) {
        case .accept:
          appendNewTranscriptSegment(newSeg, segment: segment, to: &segmentsToPersist)

        case .suppressIncoming:
          log(
            "Transcript [DEDUP] Suppressed mic playback duplicate [\(String(format: "%.1f", segment.start))s-\(String(format: "%.1f", segment.end))s]"
          )

        case .replaceExisting(let existingSegmentId):
          guard let existingIdx = speakerSegments.firstIndex(where: { $0.segmentId == existingSegmentId }) else {
            appendNewTranscriptSegment(newSeg, segment: segment, to: &segmentsToPersist)
            continue
          }

          let oldWords = speakerSegments[existingIdx].text.split(separator: " ").count
          let newWords = newSeg.text.split(separator: " ").count
          totalWordCount += newWords - oldWords

          var replacement = newSeg
          replacement.segmentId = existingSegmentId
          speakerSegments[existingIdx] = replacement
          segmentsToPersist.append(segmentWithID(segment, id: existingSegmentId))
          log(
            "Transcript [DEDUP] Promoted system-audio copy over mic playback duplicate [\(String(format: "%.1f", segment.start))s-\(String(format: "%.1f", segment.end))s]"
          )
        }
      } else {
        appendNewTranscriptSegment(newSeg, segment: segment, to: &segmentsToPersist)
      }
    }

    // Sliding window: trim old segments from memory (they're already persisted in SQLite)
    if speakerSegments.count > maxInMemorySegments {
      let excess = speakerSegments.count - maxInMemorySegments
      speakerSegments.removeFirst(excess)
    }

    log(
      "Transcript [SEGMENTS] Total: \(totalSegmentCount) segments (in-memory: \(speakerSegments.count))"
    )

    // Update published segments for UI (via isolated monitor)
    LiveTranscriptMonitor.shared.updateSegments(speakerSegments)

    // Persist segments to DB for crash safety (upsert by backend segment ID). While the
    // session id has not landed yet, hold the segments for the session instead of dropping
    // them — they are flushed the moment `currentSessionId` is installed.
    if !segmentsToPersist.isEmpty {
      if let sessionId = currentSessionId {
        enqueueTranscriptPersistence(segmentsToPersist, sessionId: sessionId)
      } else {
        holdTranscriptWorkUntilSessionExists(.segments(segmentsToPersist))
      }
    }
  }

  private func appendNewTranscriptSegment(
    _ newSegment: SpeakerSegment,
    segment: TranscriptionService.BackendSegment,
    to segmentsToPersist: inout [TranscriptionService.BackendSegment]
  ) {
    totalWordCount += newSegment.text.split(separator: " ").count
    speakerSegments.append(newSegment)
    totalSegmentCount += 1
    segmentsToPersist.append(segment)
    log(
      "Transcript [ADD] Speaker \(newSegment.speaker) [\(String(format: "%.1f", newSegment.start))s-\(String(format: "%.1f", newSegment.end))s]: \(segment.text.prefix(80))"
    )
  }

  private func segmentWithID(
    _ segment: TranscriptionService.BackendSegment,
    id: String
  ) -> TranscriptionService.BackendSegment {
    TranscriptionService.BackendSegment(
      id: id,
      text: segment.text,
      speaker: segment.speaker,
      speaker_id: segment.speaker_id,
      is_user: segment.is_user,
      person_id: segment.person_id,
      start: segment.start,
      end: segment.end,
      translations: segment.translations
    )
  }

  /// On-device diarization moved already-emitted segments to other speakers — typically the
  /// provisional "You" turned out to be the other person in the room. Rewrites the live
  /// transcript in memory and the current session's rows, in the persistence queue so a
  /// still-pending upsert of an old segment cannot land after the relabel and undo it.
  func applyLocalSpeakerRelabels(_ relabels: [Int: LocalSpeakerRegistry.Resolution]) {
    guard !relabels.isEmpty else { return }
    var moved = 0
    for index in speakerSegments.indices {
      guard let target = relabels[speakerSegments[index].speaker] else { continue }
      speakerSegments[index].speaker = target.speakerId
      speakerSegments[index].isUser = target.isUser
      speakerSegments[index].personId = target.personId
      moved += 1
    }
    // The live name map is keyed by speaker id; move the names with the ids. Cleared in a
    // pass of its own before anything is written: a swap (0↔1) visits both ends, and
    // clearing one while writing the other would let dictionary order decide whether the
    // second entry wipes what the first just wrote. Ids no relabel mentions keep their name.
    for from in relabels.keys {
      liveSpeakerPersonMap[from] = nil
    }
    for target in relabels.values {
      liveSpeakerPersonMap[target.speakerId] = target.personId
    }
    let summary = relabels.map {
      "\($0.key)→\($0.value.speakerId)\($0.value.isUser ? "(you)" : "")\($0.value.personId.map { " person=\($0)" } ?? "")"
    }
    .sorted().joined(separator: " ")
    log("Transcript [RELABEL] \(summary): \(moved) in-memory segments moved")
    if moved > 0 {
      LiveTranscriptMonitor.shared.updateSegments(speakerSegments)
    }
    guard let sessionId = currentSessionId else {
      // The session id has not landed yet. The moved bubbles are on screen; hold the
      // storage-level relabel so it reaches the stored rows in arrival order once the
      // session exists, instead of being dropped with them.
      holdTranscriptWorkUntilSessionExists(.relabels(relabels))
      return
    }
    enqueueRelabelPersistence(sessionId: sessionId, relabels: relabels)
  }

  /// "This is me" on a live bubble: the on-device diarizer makes that speaker the user and
  /// remembers the voice, and every earlier bubble moves accordingly.
  func markLiveSpeakerAsUser(_ speakerId: Int) {
    Task { @MainActor [weak self] in
      let relabels = await LocalSpeakerDiarizer.shared.markSpeakerAsUser(speakerId)
      self?.applyLocalSpeakerRelabels(relabels)
    }
  }

  /// A live speaker was named. Shows the name now and, on the on-device path, teaches the
  /// diarizer that person's voice so it is stamped automatically next time.
  func assignLiveSpeaker(_ speakerId: Int, toPerson personId: String?) {
    liveSpeakerPersonMap[speakerId] = personId
    guard sttSession.useLocalSTT else { return }
    Task { @MainActor [weak self] in
      let relabels = await LocalSpeakerDiarizer.shared.assignPerson(personId, toSpeaker: speakerId)
      self?.applyLocalSpeakerRelabels(relabels)
    }
  }

  private func enqueueTranscriptPersistence(
    _ segments: [TranscriptionService.BackendSegment],
    sessionId: Int64
  ) {
    enqueueTranscriptStorageWork { [weak self] in
      await self?.persistBackendSegmentsToStorage(segments, sessionId: sessionId)
    }
  }

  private func enqueueRelabelPersistence(
    sessionId: Int64,
    relabels: [Int: LocalSpeakerRegistry.Resolution]
  ) {
    enqueueTranscriptStorageWork {
      do {
        let rows = try await TranscriptionStorage.shared.relabelSpeakers(sessionId: sessionId, relabels: relabels)
        log("Transcript [RELABEL] \(rows) stored segments moved in session \(sessionId)")
      } catch {
        logError("Transcript [RELABEL] failed to persist speaker relabel", error: error)
      }
    }
  }

  /// Hold transcript storage work that arrived before the DB session existed, so a segment
  /// or relabel is never silently dropped for racing the async session creation. Only an
  /// active recording holds work — one that already stopped will never have a session.
  private func holdTranscriptWorkUntilSessionExists(_ unit: HeldTranscriptWorkUnit) {
    guard isTranscribing else { return }
    heldTranscriptWork.append(unit)
    switch unit {
    case .segments(let segments):
      log("Transcript [HOLD] \(segments.count) segment(s) held until the DB session exists")
    case .relabels:
      log("Transcript [HOLD] speaker relabel(s) held until the DB session exists")
    }
  }

  /// Flush held transcript work into the freshly created session, preserving arrival order
  /// so a held relabel still lands after the held segments it renames. Called right after
  /// `currentSessionId` is installed by the session-creation tasks.
  func flushHeldTranscriptWork(sessionId: Int64) {
    guard !heldTranscriptWork.isEmpty else { return }
    let units = heldTranscriptWork
    heldTranscriptWork = []
    for unit in units {
      switch unit {
      case .segments(let segments):
        enqueueTranscriptPersistence(segments, sessionId: sessionId)
      case .relabels(let relabels):
        enqueueRelabelPersistence(sessionId: sessionId, relabels: relabels)
      }
    }
    log("Transcript [HOLD] flushed \(units.count) held unit(s) into session \(sessionId)")
  }

  /// Drop held transcript work when the recording that would have created its session ends
  /// without one — it has nowhere to land and must not leak into an unrelated recording.
  func discardHeldTranscriptWork() {
    guard !heldTranscriptWork.isEmpty else { return }
    heldTranscriptWork = []
    log("Transcript [HOLD] discarded held transcript work — no session will exist for it")
  }

  /// Serialize transcript storage writes: each unit runs after every earlier one finished.
  private func enqueueTranscriptStorageWork(_ work: @escaping @MainActor () async -> Void) {
    let previous = transcriptPersistenceTail
    transcriptPersistenceTail = Task { @MainActor in
      await previous?.value
      await work()
    }
  }

  func flushTranscriptPersistence() async {
    await transcriptPersistenceTail?.value
  }

  func persistBackendSegmentsToStorage(
    _ segments: [TranscriptionService.BackendSegment],
    sessionId: Int64
  ) async {
    for segment in segments {
      guard !segment.text.isEmpty else { continue }
      let speakerId = segment.speaker_id ?? 0
      var translationsJson: String?
      if let translations = segment.translations, !translations.isEmpty {
        let mapped = translations.map { TranscriptTranslation(lang: $0.lang, text: $0.text) }
        if let data = try? JSONEncoder().encode(mapped) {
          translationsJson = String(data: data, encoding: .utf8)
        }
      }
      do {
        try await TranscriptionStorage.shared.upsertSegment(
          sessionId: sessionId,
          backendSegmentId: segment.id,
          speaker: speakerId,
          text: segment.text,
          startTime: segment.start,
          endTime: segment.end,
          isUser: segment.is_user,
          personId: segment.person_id,
          speakerLabel: segment.speaker,
          translationsJson: translationsJson
        )
      } catch {
        logError("Transcription: Failed to persist segment to DB", error: error)
        await RewindDatabase.shared.reportQueryError(error)
      }
    }
  }

  func bindActiveSessionToBackendConversation(_ backendId: String) {
    guard
      DesktopConversationMatchPolicy.shouldBindConversationSession(
        incomingBackendId: backendId,
        expectedBackendId: currentClientConversationId,
        activeBackendId: currentBackendConversationId,
        ignoredRotatedBackendIds: ignoredRotatedBackendConversationIds
      )
    else {
      pendingBackendConversationId = nil
      // A repeated callback for an already-ignored rollover is harmless. Do
      // not evict an unrelated guard entry just because that stale callback
      // arrived again; eviction is reserved for a newly observed rotation.
      ignoredRotatedBackendConversationIds = DesktopConversationMatchPolicy.rememberingRotatedBackendId(
        backendId,
        activeBackendId: currentBackendConversationId,
        ignoredRotatedBackendIds: ignoredRotatedBackendConversationIds,
        maxCount: Self.maxIgnoredRotatedBackendConversationIds
      )
      log("Transcription: Ignoring non-matching backend conversation id \(backendId) for current local session")
      return
    }

    ignoredRotatedBackendConversationIds = []
    currentBackendConversationId = backendId

    guard let sessionId = currentSessionId else {
      pendingBackendConversationId = backendId
      log("Transcription: Deferred backend conversation bind until local DB session exists (backend: \(backendId))")
      return
    }

    pendingBackendConversationId = nil
    Task {
      do {
        try await TranscriptionStorage.shared.bindBackendConversation(id: sessionId, backendId: backendId)
      } catch {
        logError(
          "Transcription: Failed to bind DB session \(sessionId) to backend conversation \(backendId)", error: error)
      }
    }
  }

  /// Reject out-of-order versioned lifecycle events before they can mutate UI
  /// or local-session display state. Events without the additive envelope keep
  /// the established legacy identity/timestamp compatibility behavior.
  func acceptsLifecycleEnvelope(
    _ event: TranscriptionService.ListenEvent,
    conversationId: String,
    expectedLifecyclePhase: String,
    expectedBackendId: String?
  ) -> Bool {
    let recordingSessionId = event.raw["recording_session_id"] as? String
    let lifecycleVersion = event.raw["lifecycle_version"] as? Int
    let lifecyclePhase = event.raw["lifecycle_phase"] as? String
    let lifecycleSequence = event.raw["lifecycle_sequence"] as? Int
    let lastAcceptedSequence = recordingSessionId.flatMap { lifecycleSequenceByRecordingSession[$0] }
    guard
      DesktopConversationMatchPolicy.acceptsLifecycleEnvelope(
        recordingSessionId: recordingSessionId,
        conversationId: conversationId,
        lifecycleVersion: lifecycleVersion,
        lifecyclePhase: lifecyclePhase,
        lifecycleSequence: lifecycleSequence,
        expectedLifecyclePhase: expectedLifecyclePhase,
        expectedBackendId: expectedBackendId,
        lastAcceptedSequence: lastAcceptedSequence
      )
    else {
      log("Transcription: Ignoring stale or misbound versioned lifecycle event for \(conversationId)")
      return false
    }
    if let recordingSessionId, let lifecycleSequence {
      if lifecycleSequenceByRecordingSession.count >= Self.maxLifecycleRecordingSessions,
        lifecycleSequenceByRecordingSession[recordingSessionId] == nil,
        let evicted = lifecycleSequenceByRecordingSession.keys.first
      {
        lifecycleSequenceByRecordingSession.removeValue(forKey: evicted)
      }
      lifecycleSequenceByRecordingSession[recordingSessionId] = lifecycleSequence
    }
    return true
  }

  /// Handle message events from Python backend `/v4/listen`
  func handleListenEvent(_ event: TranscriptionService.ListenEvent) {
    switch event.type {
    case "service_status":
      let status = event.raw["status"] as? String ?? "unknown"
      if status == "stt_failed" {
        // The socket is closed immediately after this status. Keep a
        // user-visible truth state through reconnects; only a subsequent
        // ready status proves that live transcription recovered.
        transcriptionServiceError = "Transcription unavailable"
      } else if status == "ready" {
        transcriptionServiceError = nil
      }
      log("Transcription: Backend service status: \(status)")

    case "conversation_session":
      guard let backendId = event.raw["conversation_id"] as? String, !backendId.isEmpty else {
        log("Transcription: Ignoring conversation_session event without conversation_id")
        break
      }
      guard
        acceptsLifecycleEnvelope(
          event,
          conversationId: backendId,
          expectedLifecyclePhase: "in_progress",
          expectedBackendId: currentClientConversationId
        )
      else {
        break
      }
      bindActiveSessionToBackendConversation(backendId)

    case "memory_processing_started":
      // ConversationEvent: conversation is nested under "memory"
      let memory = event.raw["memory"] as? [String: Any]
      let processingId = memory?["id"] as? String ?? "?"
      let recordingSessionId = event.raw["recording_session_id"] as? String
      let conversationId = event.raw["conversation_id"] as? String ?? processingId
      guard conversationId == processingId,
        acceptsLifecycleEnvelope(
          event,
          conversationId: conversationId,
          expectedLifecyclePhase: "processing",
          expectedBackendId: currentClientConversationId
        )
      else {
        break
      }
      guard
        DesktopConversationMatchPolicy.lifecycleEventBelongsToRecording(
          memoryId: processingId,
          recordingSessionId: recordingSessionId,
          expectedBackendId: currentClientConversationId
        )
      else {
        log("Transcription: Ignoring stale memory_processing_started \(processingId) for current recording")
        break
      }
      log("Transcription: Backend started processing conversation: \(processingId)")
      isSavingConversation = true

    case "memory_created":
      // ConversationEvent: conversation is nested under "memory"
      let memory = event.raw["memory"] as? [String: Any]
      let memoryId = memory?["id"] as? String ?? "?"
      let recordingSessionId = event.raw["recording_session_id"] as? String
      log("Transcription: Backend created conversation: \(memoryId)")

      // Mark DB session as completed so TranscriptionRetryService won't re-upload.
      // Only bind the session captured before rotation; live events may arrive while
      // the next recording is already active.
      let conversationId = event.raw["conversation_id"] as? String ?? memoryId
      guard conversationId == memoryId,
        let targetIndex = DesktopConversationMatchPolicy.matchingFinishedRecordingIndex(
          memoryId: memoryId,
          memory: memory,
          recordingSessionId: recordingSessionId,
          pending: pendingFinishedRecordings
        )
      else {
        log("Transcription: Ignoring memory_created \(memoryId); no matching finished local recording")
        break
      }
      let target = pendingFinishedRecordings[targetIndex]
      guard
        acceptsLifecycleEnvelope(
          event,
          conversationId: conversationId,
          expectedLifecyclePhase: "completed",
          expectedBackendId: target.clientConversationId
        )
      else {
        break
      }

      isSavingConversation = false
      pendingFinishedRecordings.remove(at: targetIndex)
      if let recordingSessionId {
        lifecycleSequenceByRecordingSession.removeValue(forKey: recordingSessionId)
      }

      if let sessionId = target.sessionId {
        Task {
          do {
            try await TranscriptionStorage.shared.markSessionCompleted(
              id: sessionId, backendId: memoryId)
            log("Transcription: Marked DB session \(sessionId) completed (backend: \(memoryId))")
          } catch {
            logError(
              "Transcription: Failed to mark DB session \(sessionId) completed", error: error)
          }
        }
      } else {
        log("Transcription: Accepted memory_created \(memoryId) without a durable local session")
        AnalyticsManager.shared.conversationCreated(
          conversationId: memoryId,
          source: target.source.rawValue,
          durationSeconds: max(0, Int(Date().timeIntervalSince(target.startedAt)))
        )
      }

      // Check daily goal generation
      GoalGenerationService.shared.onConversationCreated()

      // Refresh conversations list
      Task {
        await loadConversations()
      }

    case "speaker_label_suggestion":
      let speakerId = event.raw["speaker_id"] as? Int ?? 0
      let personId = event.raw["person_id"] as? String
      let personName = event.raw["person_name"] as? String ?? "Unknown"
      log(
        "Transcription: Speaker \(speakerId) identified as \(personName) (person_id: \(personId ?? "nil"))"
      )
      // Update live speaker-person mapping
      if let personId = personId {
        liveSpeakerPersonMap[speakerId] = personId
      }

    case "segments_deleted":
      if let segmentIds = event.raw["segment_ids"] as? [String] {
        log("Transcription: Backend deleted \(segmentIds.count) segments")
        // Decrement counters for deleted segments
        let deletedSegments = speakerSegments.filter { seg in
          guard let segId = seg.segmentId else { return false }
          return segmentIds.contains(segId)
        }
        let deletedWords = deletedSegments.reduce(0) { $0 + $1.text.split(separator: " ").count }
        totalWordCount = max(0, totalWordCount - deletedWords)
        totalSegmentCount = max(0, totalSegmentCount - deletedSegments.count)

        speakerSegments.removeAll { seg in
          guard let segId = seg.segmentId else { return false }
          return segmentIds.contains(segId)
        }
        LiveTranscriptMonitor.shared.updateSegments(speakerSegments)

        // Also remove from DB
        if let sessionId = currentSessionId {
          Task {
            do {
              try await TranscriptionStorage.shared.deleteSegmentsByBackendIds(
                sessionId: sessionId, segmentIds: segmentIds)
            } catch {
              logError("Transcription: Failed to delete segments from DB", error: error)
            }
          }
        }
      }

    case "freemium_threshold_reached":
      let remaining = event.raw["remaining_seconds"] as? Int ?? 0
      log("Transcription: Freemium threshold reached, \(remaining)s remaining")
      // BYOK users must never be paywalled. The backend exempts them, but a
      // heartbeat/Firestore lag can briefly let this event slip through right
      // after activation — ignore it so we don't kill a BYOK user's capture.
      if APIKeyService.hasTranscriptionBYOK {
        log("Paywall: ignoring freemium threshold — BYOK active locally")
        if isPaywalled { isPaywalled = false }
        break
      }
      triggerUsageLimitPopup(reason: "transcription")
      // Hard-stop client-side capture so the mic LED and screen-recording
      // indicator actually turn off. Without this, popup shows but the user
      // still sees the mic indicator green and assumes recording continues —
      // confusing and a battery/trust hit. Sticky until next app launch or
      // successful plan reactivation.
      isPaywalled = true
      if isTranscribing {
        log("Paywall: stopping transcription (freemium threshold)")
        stopTranscription()
      }
      Task { @MainActor in
        ProactiveAssistantsPlugin.shared.stopMonitoring(reason: .paywall)
      }

    case "translating":
      if let segmentsArray = event.raw["segments"] as? [[String: Any]] {
        do {
          let data = try JSONSerialization.data(withJSONObject: segmentsArray)
          let translatedSegments = try JSONDecoder().decode(
            [TranscriptionService.BackendSegment].self, from: data)
          log("Transcription: Translation event with \(translatedSegments.count) segments")
          for translated in translatedSegments {
            guard let segId = translated.id else { continue }
            let newTranslations = (translated.translations ?? []).map {
              SegmentTranslation(lang: $0.lang, text: $0.text)
            }
            guard !newTranslations.isEmpty else { continue }

            // Update in-memory if the segment is still loaded
            if let idx = speakerSegments.firstIndex(where: { $0.segmentId == segId }) {
              speakerSegments[idx].translations = newTranslations
            }

            // Always persist to SQLite — even if the segment was trimmed from
            // the in-memory window, the event payload has all fields needed
            if let sessionId = currentSessionId {
              let mapped = newTranslations.map { TranscriptTranslation(lang: $0.lang, text: $0.text) }
              let translationsJson = (try? JSONEncoder().encode(mapped))
                .flatMap { String(data: $0, encoding: .utf8) }
              Task {
                try? await TranscriptionStorage.shared.upsertSegment(
                  sessionId: sessionId,
                  backendSegmentId: segId,
                  speaker: translated.speaker_id ?? 0,
                  text: translated.text,
                  startTime: translated.start,
                  endTime: translated.end,
                  isUser: translated.is_user,
                  personId: translated.person_id,
                  speakerLabel: translated.speaker,
                  translationsJson: translationsJson
                )
              }
            }
          }
          LiveTranscriptMonitor.shared.updateSegments(speakerSegments)
        } catch {
          logError("Transcription: Failed to parse translation event", error: error)
        }
      } else {
        log("Transcription: Translation event received (no segments)")
      }

    case "last_memory":
      let memoryId = event.raw["memory_id"] as? String ?? "?"
      log("Transcription: Last conversation event: \(memoryId)")

    case "photo_processing":
      log("Transcription: Photo processing event (not used on desktop)")

    case "photo_described":
      log("Transcription: Photo described event (not used on desktop)")

    case "proactive_message":
      let appId = event.raw["app_id"] as? String ?? ""
      let title = event.raw["title"] as? String ?? "Omi"
      let message = event.raw["message"] as? String ?? ""
      // The message body is user conversation content; log only its provenance.
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
      let admission = ProactiveListenAdmission.decide(
        appID: appId,
        title: title,
        message: message,
        hasRuntimeOwner: authorizationSnapshot != nil)
      guard case .deliver(let deliveryTitle, let deliveryMessage, let assistantId) = admission,
        let authorizationSnapshot
      else {
        if case .skip(let reason) = admission {
          log("Transcription: Dropping proactive_message — \(reason.rawValue)")
        }
        break
      }
      log("Transcription: Proactive message from \(assistantId)")
      // Deliver through NotificationService rather than the floating-bar primitive.
      // A cloud interjection is proactive in exactly the sense the user's controls
      // mean: routing it here keeps the master toggle, the off-by-default migration,
      // the frequency throttle, and the snooze/presence withholding on one door,
      // instead of giving the cloud a path that ignores all of them. It also owns
      // the spoken delivery (`isProactive: respectFrequency`), so the caller does
      // not need its own NotificationSpeechOnDelivery.
      NotificationService.shared.sendNotification(
        ownerID: authorizationSnapshot.ownerID,
        title: deliveryTitle,
        message: deliveryMessage,
        assistantId: assistantId,
        sound: .default,
        respectFrequency: true,
        authorizationSnapshot: authorizationSnapshot
      )

    default:
      log("Transcription: Unhandled event type: \(event.type)")
    }
  }

  /// Update the display transcript — no-op since word count is tracked incrementally
  /// and views use LiveTranscriptMonitor.segments directly
  func updateTranscriptDisplay() {
    // Previously rebuilt currentTranscript from all speakerSegments on every incoming segment,
    // causing O(N^2) string allocations. Word count is now tracked via totalWordCount.
  }

  /// Append text to transcript (fallback when no word-level data)
  func appendToTranscript(_ text: String) {
    if !currentTranscript.isEmpty {
      currentTranscript += "\n"
    }
    currentTranscript += text
  }

  /// Request microphone permission
}
