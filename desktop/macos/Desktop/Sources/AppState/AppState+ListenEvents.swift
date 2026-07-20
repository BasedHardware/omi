@preconcurrency import AVFoundation
import Combine
import SwiftUI
@preconcurrency import UserNotifications

@MainActor
extension AppState {
  func handleBackendSegments(_ segments: [TranscriptionService.BackendSegment]) {
    for segment in segments {
      guard !segment.text.isEmpty else { continue }

      // Extract speaker_id from backend (e.g. "SPEAKER_00" → 0)
      let speakerId = segment.speaker_id ?? 0

      // Convert backend segment to local SpeakerSegment
      let translations = (segment.translations ?? []).map {
        SegmentTranslation(lang: $0.lang, text: $0.text)
      }
      let newSeg = SpeakerSegment(
        segmentId: segment.id,
        speaker: speakerId,
        text: segment.text,
        start: segment.start,
        end: segment.end,
        isUser: segment.is_user,
        personId: segment.person_id,
        translations: translations
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
      } else {
        totalWordCount += newSeg.text.split(separator: " ").count
        speakerSegments.append(newSeg)
        totalSegmentCount += 1
        log(
          "Transcript [ADD] Speaker \(speakerId) [\(String(format: "%.1f", segment.start))s-\(String(format: "%.1f", segment.end))s]: \(segment.text.prefix(80))"
        )
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

    // Persist segments to DB for crash safety (upsert by backend segment ID)
    if let sessionId = currentSessionId {
      let segmentsToPersist = segments
      Task {
        await persistBackendSegmentsToStorage(segmentsToPersist, sessionId: sessionId)
      }
    }
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
      if let currentBackendConversationId, currentBackendConversationId != backendId {
        ignoredRotatedBackendConversationIds.insert(backendId)
      }
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
      let targetSessionId = finishedSessionId
      let targetClientConversationId = finishedClientConversationId
      let targetStartTime = finishedRecordingStartTime
      let didBindLocalSession: Bool
      let conversationId = event.raw["conversation_id"] as? String ?? memoryId
      guard conversationId == memoryId,
        acceptsLifecycleEnvelope(
          event,
          conversationId: conversationId,
          expectedLifecyclePhase: "completed",
          expectedBackendId: targetClientConversationId
        )
      else {
        break
      }
      if !DesktopConversationMatchPolicy.lifecycleEventBelongsToRecording(
        memoryId: memoryId,
        recordingSessionId: recordingSessionId,
        expectedBackendId: targetClientConversationId
      ) {
        log("Transcription: Ignoring stale memory_created \(memoryId) for finished recording")
        break
      }
      isSavingConversation = false
      // New desktop sessions carry an exact client-generated recording id, so
      // they must never fall back to a timestamp guess. Timestamp matching is
      // retained only for legacy sessions without that identity.
      let matchesFinishedRecording =
        targetClientConversationId != nil
        || DesktopConversationMatchPolicy.memoryEventMatchesFinishedSession(
          memory, sessionStartedAt: targetStartTime ?? .distantPast)
      if let sessionId = targetSessionId,
        memoryId != "?",
        matchesFinishedRecording
      {
        finishedSessionId = nil  // Consume once
        finishedClientConversationId = nil
        finishedRecordingStartTime = nil
        didBindLocalSession = true
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
        didBindLocalSession = false
        if memoryId != "?" {
          if targetSessionId == nil || targetStartTime == nil {
            log(
              "Transcription: Ignoring memory_created \(memoryId); no finished local session is awaiting backend binding"
            )
          } else if let sessionId = targetSessionId, let startTime = targetStartTime {
            if let memoryStartedAt = DesktopConversationMatchPolicy.parseMemoryEventDate(
              memory?["started_at"] ?? memory?["startedAt"])
            {
              let delta = abs(memoryStartedAt.timeIntervalSince(startTime))
              if delta >= DesktopConversationMatchPolicy.startedAtTolerance {
                log(
                  "Transcription: Ignoring memory_created event; started_at delta \(String(format: "%.1f", delta))s exceeds session match tolerance"
                )
              }
            }
            log(
              "Transcription: Waiting for API reconciliation before binding memory_created \(memoryId) to local session \(sessionId)"
            )
          }
        }
      }

      // Track conversation creation — use captured start time for accurate duration after session rotation
      if didBindLocalSession, let startTime = targetStartTime {
        let durationSeconds = Int(Date().timeIntervalSince(startTime))
        ActivationProgressStore.shared.markConversationCaptured(title: nil)
        AnalyticsManager.shared.conversationCreated(
          conversationId: memoryId,
          source: currentConversationSource.rawValue,
          durationSeconds: durationSeconds
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
      if APIKeyService.isByokActive {
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
        ProactiveAssistantsPlugin.shared.stopMonitoring()
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
