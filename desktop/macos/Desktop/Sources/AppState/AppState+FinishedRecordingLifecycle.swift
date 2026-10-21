import Foundation

/// Lifecycle-envelope capture for recordings that have ended locally but may
/// still be awaiting the backend's terminal `memory_created` event.
@MainActor
extension AppState {
  func captureFinishedRecordingForLifecycle(
    sessionId: Int64?,
    clientConversationId: String?,
    startedAt: Date?,
    source: ConversationSource
  ) {
    guard let startedAt else { return }
    let envelope = FinishedRecordingEnvelope(
      sessionId: sessionId,
      clientConversationId: clientConversationId,
      startedAt: startedAt,
      source: source
    )
    if pendingFinishedRecordings.contains(envelope) { return }
    if pendingFinishedRecordings.count >= Self.maxPendingFinishedRecordings {
      let evicted = pendingFinishedRecordings.removeFirst()
      log(
        "Transcription: Evicting unmatched finished-recording lifecycle envelope \(evicted.clientConversationId ?? "legacy")"
      )
    }
    pendingFinishedRecordings.append(envelope)
  }

  func captureCurrentFinishedRecordingForLifecycle() {
    // A finished recording is on its way to the list. Hold the Live card's
    // slot with the Saving card until the next conversations load lands.
    isFinalizingCapture = currentSessionId != nil
    captureFinishedRecordingForLifecycle(
      sessionId: currentSessionId,
      clientConversationId: currentClientConversationId
        ?? currentBackendConversationId
        ?? pendingBackendConversationId,
      startedAt: recordingStartTime,
      source: currentConversationSource
    )
  }

  func captureFinishedRecordingForLifecycleIfCloud(wasLocalSTT: Bool) {
    guard !wasLocalSTT else { return }
    captureCurrentFinishedRecordingForLifecycle()
  }
}
