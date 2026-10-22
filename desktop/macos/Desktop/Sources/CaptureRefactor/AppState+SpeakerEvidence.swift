import Foundation

extension AppState {
  func applyRefactorSpeakerEvent(_ raw: [String: Any]) {
    guard let speakerID = raw["speaker_id"] as? Int, speakerID >= 0 else { return }
    let personID = raw["person_id"] as? String
    let label = ResolvedSpeakerLabel(
      personID: personID, isUser: raw["is_user"] as? Bool,
      retracted: raw["retracted"] as? Bool == true)
    if label.isUser { log("event=refactor_shadow lane=L5 check=speaker_owner outcome=disagree") }
    guard ClientRefactorFlags.serving else {
      // refactor: superseded by ResolvedSpeakerLabel when clients_refactor=serve
      if let personID { liveSpeakerPersonMap[speakerID] = personID }
      return
    }
    guard liveManualSpeakerPersonMap[speakerID] == nil,
      label.retracted || label.isUser || label.personID != nil
    else { return }
    // nil removes the entry; a retraction must never store an empty person id.
    liveSpeakerPersonMap[speakerID] = label.liveMapValue
    speakerSegments = speakerSegments.map { $0.speaker == speakerID ? label.apply(to: $0) : $0 }
    LiveTranscriptMonitor.shared.updateSegments(speakerSegments)
    guard let sessionID = currentSessionId else { return }
    let generation = ownerScopeGeneration
    Task {
      guard self.ownerScopeGeneration == generation, self.currentSessionId == sessionID else { return }
      do {
        await self.flushTranscriptPersistence()
        guard self.ownerScopeGeneration == generation, self.currentSessionId == sessionID else { return }
        try await TranscriptionStorage.shared.updateLiveSpeakerAssignment(
          sessionId: sessionID, speakerId: speakerID,
          personId: personID ?? "", isUser: label.isUser, retracted: label.retracted, automatic: true)
      } catch { log("event=refactor_shadow lane=L5 check=speaker_persist outcome=error") }
    }
  }
}
