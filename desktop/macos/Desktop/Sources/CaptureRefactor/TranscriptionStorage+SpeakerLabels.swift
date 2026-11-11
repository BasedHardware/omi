import Foundation
@preconcurrency import GRDB

extension TranscriptionStorage {
  @discardableResult
  func updateLiveSpeakerAssignment(
    sessionId: Int64,
    speakerId: Int,
    personId: String,
    isUser: Bool? = nil,
    retracted: Bool = false,
    automatic: Bool = false,
    useExplicitOwner: Bool? = nil
  ) async throws -> Int {
    let db = try await ensureInitialized()
    let serving = if let useExplicitOwner { useExplicitOwner } else { await ClientRefactorFlags.serving }
    let label = ResolvedSpeakerLabel(personID: personId, isUser: isUser, retracted: retracted)
    return try await db.write { database -> Int in
      if serving {
        try database.execute(
          sql: """
            UPDATE transcription_segments SET isUser = ?, personId = ?, speakerLabelSource = ?
            WHERE sessionId = ? AND speaker = ? AND (? = 0 OR COALESCE(speakerLabelSource, '') != 'manual')
            """,
          arguments: [
            label.isUser, label.personID, retracted ? nil : automatic ? "auto" : "manual",
            sessionId, speakerId, automatic,
          ])
        return database.changesCount
      }
      // refactor: superseded by ResolvedSpeakerLabel when clients_refactor=serve
      try database.execute(
        sql: """
          UPDATE transcription_segments
          SET isUser = ?, personId = ?, speakerLabelSource = 'manual'
          WHERE sessionId = ? AND speaker = ?
          """,
        arguments: [false, personId, sessionId, speakerId]
      )
      return database.changesCount
    }
  }

  /// Replaces backend-owned transcript fields while preserving existing local speaker assignments.
  /// Skips when incoming segments are empty to avoid wiping locally-cached data
  /// (list endpoints often return conversations without transcript segments).
  func upsertSegmentsFromServerConversation(
    _ conversation: ServerConversation,
    sessionId: Int64,
    cacheScope: ConversationCacheWriteScope? = nil,
    cacheGeneration: Int? = nil,
    useSegmentIdentity: Bool? = nil
  ) async throws {
    guard !conversation.transcriptSegments.isEmpty else { return }

    let db = try await ensureInitialized()
    let serving = if let useSegmentIdentity { useSegmentIdentity } else { await ClientRefactorFlags.serving }

    try await db.write { database in
      try withConversationCacheScope(cacheScope, generation: cacheGeneration) {
        guard let session = try TranscriptionSessionRecord.fetchOne(database, key: sessionId), !session.deleted else {
          return
        }
        let existingSegments =
          try TranscriptionSegmentRecord
          .filter(Column("sessionId") == sessionId)
          .fetchAll(database)
        var existingBySegmentId: [String: TranscriptionSegmentRecord] = [:]
        var existingByOrder: [Int: TranscriptionSegmentRecord] = [:]
        for segment in existingSegments {
          if let segmentId = segment.segmentId {
            existingBySegmentId[segmentId] = segment
          }
          existingByOrder[segment.segmentOrder] = segment
        }

        // Delete existing segments for this session
        try database.execute(
          sql: "DELETE FROM transcription_segments WHERE sessionId = ?",
          arguments: [sessionId]
        )

        // Insert new segments
        for (index, segment) in conversation.transcriptSegments.enumerated() {
          var record = TranscriptionSegmentRecord.from(segment, sessionId: sessionId, segmentOrder: index)
          let exact = segment.backendId.flatMap { existingBySegmentId[$0] }
          let proposed = ServerSegmentLabelMerge.merge(record, existing: exact)
          let legacy = exact ?? existingByOrder[index]
          let agrees =
            !((legacy?.hasSpeakerAssignment == true)
            && (proposed.isUser != legacy?.isUser || proposed.personId != legacy?.personId))
          if !agrees { log("event=refactor_shadow lane=L5 check=label_graft outcome=disagree") }
          if serving {
            record = proposed
            // refactor: superseded by ServerSegmentLabelMerge when clients_refactor=serve
          } else if let existing = exact ?? existingByOrder[index], existing.hasSpeakerAssignment {
            record.isUser = existing.isUser
            record.personId = existing.personId
          }
          _ = try record.inserted(database)
        }

        log("TranscriptionStorage: Upserted \(conversation.transcriptSegments.count) segments for session \(sessionId)")
      }
    }
    if let session = try await getSession(id: sessionId), session.status == .completed {
      LocalEmbeddingIndexer.scheduleFinalizedSessionIndex(sessionId: sessionId)
    }
  }

}
