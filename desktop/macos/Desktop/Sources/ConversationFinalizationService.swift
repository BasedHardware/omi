import Foundation

actor ConversationFinalizationService {
  static let shared = ConversationFinalizationService()

  private let maxRetries = 5
  private let maxLocalFallbackRetries = 3
  private var apiClient = APIClient.shared

  private init() {}

  func setAPIClientForTesting(_ client: APIClient?) {
    apiClient = client ?? APIClient.shared
  }

  func finalizeSession(
    id sessionId: Int64,
    reason: TranscriptionFinalizationReason,
    allowCloudForceProcess: Bool = false
  ) async {
    do {
      guard let session = try await TranscriptionStorage.shared.getSession(id: sessionId) else {
        return
      }
      await finalizeSession(session, reason: reason, allowCloudForceProcess: allowCloudForceProcess)
    } catch {
      logError("ConversationFinalization: Failed to load session \(sessionId)", error: error)
    }
  }

  func recoverPendingFinalizations() async {
    do {
      let sessions = try await TranscriptionStorage.shared.getSessionsNeedingFinalization(maxRetries: maxRetries)
      let exhaustedLocalFallbackSessions = try await TranscriptionStorage.shared
        .getExhaustedCloudSessionsWithLocalSegments(
          maxRetries: maxRetries,
          maxLocalFallbackRetries: maxLocalFallbackRetries
        )
      let sessionsById = Dictionary(
        grouping: sessions + exhaustedLocalFallbackSessions,
        by: { $0.id ?? -1 }
      ).compactMap { $0.value.first }

      if !sessionsById.isEmpty {
        log(
          "ConversationFinalization: Recovering \(sessionsById.count) pending sessions (\(exhaustedLocalFallbackSessions.count) exhausted cloud sessions have local fallback data)"
        )
      }
      let exhaustedLocalFallbackIds = Set(exhaustedLocalFallbackSessions.compactMap(\.id))
      for session in sessionsById where session.isReadyForRetry() || session.status != .failed || session.retryCount >= maxRetries {
        if let sessionId = session.id, exhaustedLocalFallbackIds.contains(sessionId) {
          await finalizeExhaustedCloudSessionFromLocalSegments(session)
          continue
        }
        await finalizeSession(
          session,
          reason: .retry,
          allowCloudForceProcess: session.backendId?.isEmpty == false
        )
      }
    } catch {
      logError("ConversationFinalization: Recovery failed", error: error)
    }
  }

  private func finalizeExhaustedCloudSessionFromLocalSegments(_ session: TranscriptionSessionRecord) async {
    guard let sessionId = session.id else { return }
    guard session.status != .completed && !session.backendSynced else { return }

    log("ConversationFinalization: Retrying exhausted cloud session \(sessionId) from saved local segments")

    do {
      guard try await TranscriptionStorage.shared.markSessionUploading(id: sessionId) else {
        return
      }
      guard let latestSession = try await TranscriptionStorage.shared.getSession(id: sessionId) else {
        throw TranscriptionStorageError.sessionNotFound
      }
      guard try await resolveExhaustedCloudReconciliation(session: latestSession, sessionId: sessionId) else {
        throw TranscriptionStorageError.invalidState("Exhausted cloud session has no local fallback")
      }
    } catch {
      await markRetryableFailure(sessionId: sessionId, error: error)
    }
  }

  private func finalizeSession(
    _ session: TranscriptionSessionRecord,
    reason: TranscriptionFinalizationReason,
    allowCloudForceProcess: Bool
  ) async {
    guard let sessionId = session.id else { return }
    guard session.status != .completed && !session.backendSynced else { return }

    let strategy = session.finalizationStrategy ?? defaultStrategy(for: session)
    log(
      "ConversationFinalization: Finalizing session \(sessionId) strategy=\(strategy.rawValue) reason=\(reason.rawValue)"
    )

    do {
      guard try await TranscriptionStorage.shared.markSessionUploading(id: sessionId) else {
        return
      }
      switch strategy {
      case .localSegments:
        try await uploadLocalSegments(sessionId: sessionId)
      case .cloudReconcile:
        guard let latestSession = try await TranscriptionStorage.shared.getSession(id: sessionId) else {
          throw TranscriptionStorageError.sessionNotFound
        }
        try await finalizeCloudSession(session: latestSession, allowForceProcess: allowCloudForceProcess)
      }
    } catch {
      await markRetryableFailure(sessionId: sessionId, error: error)
    }
  }

  private func defaultStrategy(for session: TranscriptionSessionRecord) -> TranscriptionFinalizationStrategy {
    if session.backendId?.isEmpty == false {
      return .cloudReconcile
    }
    return session.source == ConversationSource.desktop.rawValue ? .localSegments : .cloudReconcile
  }

  private func uploadLocalSegments(sessionId: Int64, allowBackendIdOverride: Bool = false) async throws {
    guard let bundle = try await TranscriptionStorage.shared.getSessionWithSegments(id: sessionId) else {
      throw TranscriptionStorageError.sessionNotFound
    }
    guard !bundle.segments.isEmpty else {
      log("ConversationFinalization: Deleting empty local session \(sessionId)")
      try await TranscriptionStorage.shared.deleteSession(id: sessionId)
      return
    }

    var merged: [APIClient.UploadSegment] = []
    for seg in bundle.segments {
      let upload = APIClient.UploadSegment(
        text: seg.text,
        speaker: seg.speakerLabel ?? String(format: "SPEAKER_%02d", seg.speaker),
        speaker_id: seg.speaker,
        is_user: seg.isUser,
        person_id: seg.personId,
        start: seg.startTime,
        end: seg.endTime
      )
      if let last = merged.last,
         last.speaker_id == upload.speaker_id,
         last.speaker == upload.speaker,
         last.is_user == upload.is_user,
         last.person_id == upload.person_id {
        merged[merged.count - 1] = APIClient.UploadSegment(
          text: last.text + " " + upload.text,
          speaker: last.speaker,
          speaker_id: last.speaker_id,
          is_user: last.is_user,
          person_id: last.person_id,
          start: last.start,
          end: upload.end
        )
      } else {
        merged.append(upload)
      }
    }

    let uploadSegments = Self.compactSegmentsForBackendLimit(merged)
    if uploadSegments.count != merged.count {
      log(
        "ConversationFinalization: Compacted local session \(sessionId) from \(merged.count) to \(uploadSegments.count) segments for backend upload"
      )
    }

    let iso = ISO8601DateFormatter()
    let request = APIClient.CreateConversationFromSegmentsRequest(
      transcript_segments: uploadSegments,
      source: bundle.session.source,
      started_at: iso.string(from: bundle.session.startedAt),
      finished_at: bundle.session.finishedAt.map { iso.string(from: $0) },
      language: bundle.session.language,
      client_conversation_id: Self.localClientConversationId(session: bundle.session, sessionId: sessionId)
    )
    let response = try await apiClient.createConversationFromSegments(request)
    let status = LocalConversationStatus(rawValue: response.status) ?? .processing
    let completed = try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId,
      backendId: response.id,
      conversationStatus: status,
      allowBackendIdOverride: allowBackendIdOverride
    )
    if completed {
      log("ConversationFinalization: Uploaded local session \(sessionId) -> backend conversation \(response.id)")
    }
  }

  static func compactSegmentsForBackendLimit(
    _ segments: [APIClient.UploadSegment],
    maxSegments: Int = 500
  ) -> [APIClient.UploadSegment] {
    guard maxSegments > 0, segments.count > maxSegments else { return segments }

    var compacted: [APIClient.UploadSegment] = []
    compacted.reserveCapacity(maxSegments)
    for index in 0..<maxSegments {
      let startIndex = index * segments.count / maxSegments
      let endIndex = (index + 1) * segments.count / maxSegments
      let group = Array(segments[startIndex..<endIndex])
      guard let first = group.first, let last = group.last else { continue }

      let sameSpeaker = group.allSatisfy { segment in
        segment.speaker == first.speaker
          && segment.speaker_id == first.speaker_id
          && segment.is_user == first.is_user
          && segment.person_id == first.person_id
      }
      compacted.append(
        APIClient.UploadSegment(
          text: group.map(\.text).joined(separator: " "),
          speaker: sameSpeaker ? first.speaker : "MIXED",
          speaker_id: sameSpeaker ? first.speaker_id : nil,
          is_user: sameSpeaker ? first.is_user : false,
          person_id: sameSpeaker ? first.person_id : nil,
          start: first.start,
          end: last.end
        )
      )
    }
    return compacted
  }

  private func finalizeCloudSession(
    session: TranscriptionSessionRecord,
    allowForceProcess: Bool
  ) async throws {
    guard let sessionId = session.id else { return }

    if let backendId = session.backendId, !backendId.isEmpty {
      let conversation: ServerConversation
      if allowForceProcess {
        conversation = try await apiClient.finalizeConversation(id: backendId)
      } else {
        conversation = try await apiClient.getConversation(id: backendId)
      }
      if DesktopConversationMatchPolicy.canCompleteBoundBackendConversation(
        id: conversation.id,
        boundBackendId: backendId,
        status: conversation.status,
        source: conversation.source
      ) {
        let status = LocalConversationStatus(rawValue: conversation.status.rawValue) ?? .processing
        try await TranscriptionStorage.shared.markSessionCompleted(
          id: sessionId,
          backendId: conversation.id,
          conversationStatus: status
        )
        log("ConversationFinalization: Finalized cloud session \(sessionId) by backend id \(conversation.id)")
        return
      }
      throw TranscriptionStorageError.invalidState("Bound backend conversation is not completed")
    }

    if let clientConversationId = session.clientConversationId, !clientConversationId.isEmpty {
      if try await completeCloudConversation(
        id: clientConversationId,
        sessionId: sessionId,
        allowForceProcess: true
      ) {
        return
      }
    }

    if allowForceProcess, let conversation = try await apiClient.forceProcessConversation() {
      if DesktopConversationMatchPolicy.matchesDesktopConversation(
        startedAt: conversation.startedAt,
        source: conversation.source,
        sessionStartedAt: session.startedAt
      ) {
        let status = LocalConversationStatus(rawValue: conversation.status.rawValue) ?? .processing
        try await TranscriptionStorage.shared.markSessionCompleted(
          id: sessionId,
          backendId: conversation.id,
          conversationStatus: status
        )
        log("ConversationFinalization: Force-processed unbound cloud session \(sessionId) -> \(conversation.id)")
        return
      }
    }

    let finishedAt = session.finishedAt ?? session.startedAt.addingTimeInterval(1)
    let existing = try await apiClient.getConversations(
      limit: 5,
      statuses: DesktopConversationMatchPolicy.cloudReconciliationStatuses,
      includeDiscarded: true,
      startDate: session.startedAt.addingTimeInterval(-5),
      endDate: finishedAt.addingTimeInterval(5)
    )
    let timestampMatches = existing.filter { conv in
      DesktopConversationMatchPolicy.matchesDesktopConversation(
        startedAt: conv.startedAt,
        source: conv.source,
        sessionStartedAt: session.startedAt
      )
    }
    for match in timestampMatches {
      if try await completeTimestampMatchedConversation(match, sessionId: sessionId) {
        return
      }
    }

    if session.retryCount >= maxRetries - 1 {
      if let clientConversationId = session.clientConversationId, !clientConversationId.isEmpty {
        if try await completeCloudConversation(
          id: clientConversationId,
          sessionId: sessionId,
          allowForceProcess: true
        ) {
          return
        }
      }
      if try await resolveExhaustedCloudReconciliation(session: session, sessionId: sessionId) {
        return
      }
    }

    throw TranscriptionStorageError.invalidState("No matching backend conversation found")
  }

  private func completeTimestampMatchedConversation(
    _ match: ServerConversation,
    sessionId: Int64
  ) async throws -> Bool {
    let conversation: ServerConversation
    if DesktopConversationMatchPolicy.shouldFinalizeTimestampMatchedConversation(status: match.status) {
      conversation = try await apiClient.finalizeConversation(id: match.id)
    } else {
      conversation = match
    }

    guard DesktopConversationMatchPolicy.canCompleteTimestampMatchedConversation(
      status: conversation.status,
      source: conversation.source
    ), conversation.id == match.id else {
      return false
    }

    let status = LocalConversationStatus(rawValue: conversation.status.rawValue) ?? .processing
    try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId,
      backendId: conversation.id,
      conversationStatus: status
    )
    log("ConversationFinalization: Reconciled cloud session \(sessionId) by timestamp \(conversation.id)")
    return true
  }

  @discardableResult
  func resolveExhaustedCloudReconciliation(
    session: TranscriptionSessionRecord,
    sessionId: Int64
  ) async throws -> Bool {
    let segmentCount = try await TranscriptionStorage.shared.getSegmentCount(sessionId: sessionId)
    switch Self.cloudReconciliationExhaustionAction(session: session, segmentCount: segmentCount) {
    case .keepRetrying:
      return false
    case .uploadLocalSegments:
      log(
        "ConversationFinalization: Cloud reconciliation exhausted for session \(sessionId); uploading \(segmentCount) saved local segments"
      )
      try await uploadLocalSegments(
        sessionId: sessionId,
        allowBackendIdOverride: session.backendId?.isEmpty == false
      )
      return true
    case .discardEmptyDesktopSession:
      log("ConversationFinalization: Deleting empty unreconciled desktop session \(sessionId)")
      try await TranscriptionStorage.shared.deleteSession(id: sessionId)
      return true
    case .reportFailure:
      return false
    }
  }

  enum CloudReconciliationExhaustionAction: Equatable {
    case keepRetrying
    case uploadLocalSegments
    case discardEmptyDesktopSession
    case reportFailure
  }

  static func cloudReconciliationExhaustionAction(
    session: TranscriptionSessionRecord,
    segmentCount: Int,
    maxRetries: Int = 5
  ) -> CloudReconciliationExhaustionAction {
    guard session.retryCount >= maxRetries - 1 else {
      return .keepRetrying
    }
    guard segmentCount == 0 else {
      return .uploadLocalSegments
    }
    guard session.source == ConversationSource.desktop.rawValue else {
      return .reportFailure
    }
    return .discardEmptyDesktopSession
  }

  private func completeCloudConversation(
    id conversationId: String,
    sessionId: Int64,
    allowForceProcess: Bool
  ) async throws -> Bool {
    let conversation: ServerConversation
    do {
      if allowForceProcess {
        conversation = try await apiClient.finalizeConversation(id: conversationId)
      } else {
        conversation = try await apiClient.getConversation(id: conversationId)
      }
    } catch APIError.httpError(let statusCode, _) where statusCode == 404 {
      return false
    }

    guard DesktopConversationMatchPolicy.canCompleteBoundBackendConversation(
      id: conversation.id,
      boundBackendId: conversationId,
      status: conversation.status,
      source: conversation.source
    ) else {
      return false
    }

    let status = LocalConversationStatus(rawValue: conversation.status.rawValue) ?? .processing
    try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId,
      backendId: conversation.id,
      conversationStatus: status
    )
    log("ConversationFinalization: Reconciled cloud session \(sessionId) by conversation id \(conversation.id)")
    return true
  }

  private func markRetryableFailure(sessionId: Int64, error: Error) async {
    let message = error.localizedDescription
    do {
      let session = try await TranscriptionStorage.shared.getSession(id: sessionId)
      let retryCount = (session?.retryCount ?? 0) + 1
      if retryCount >= maxRetries {
        let segmentCount = try? await TranscriptionStorage.shared.getSegmentCount(sessionId: sessionId)
        let diagnostics = ReconciliationFailureDiagnostics(
          session: session,
          segmentCount: segmentCount,
          retryCount: retryCount,
          maxRetries: maxRetries,
          maxLocalFallbackRetries: maxLocalFallbackRetries
        )
        await AnalyticsManager.shared.conversationReconciliationFailed(
          error: "session_reconciliation_failed",
          reason: "cloud_reconcile_exhausted",
          source: session?.source,
          stage: session?.finalizationStrategy?.rawValue,
          retryCount: retryCount,
          hasBackendId: session?.backendId?.isEmpty == false,
          hasClientConversationId: session?.clientConversationId?.isEmpty == false,
          segmentCount: segmentCount,
          diagnostics: diagnostics
        )
      }
      try await TranscriptionStorage.shared.incrementRetryCount(id: sessionId)
      try await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: message)
    } catch {
      logError("ConversationFinalization: Failed to record finalization failure for session \(sessionId)", error: error)
    }
  }

  static func localClientConversationId(session: TranscriptionSessionRecord, sessionId: Int64) -> String {
    let startedAtMs = Int64((session.startedAt.timeIntervalSince1970 * 1000).rounded())
    return session.clientConversationId ?? "macos-local-\(sessionId)-\(startedAtMs)"
  }
}

struct ReconciliationFailureDiagnostics {
  let sessionStatus: String?
  let conversationStatus: String?
  let finalizationReason: String?
  let hasFinishedAt: Bool
  let hasFinalizationStartedAt: Bool
  let hasFinalizationCompletedAt: Bool
  let hasInputDeviceName: Bool
  let hasLocalSegments: Bool?
  let sessionAgeSeconds: Int?
  let sessionDurationSeconds: Int?
  let localFallbackAvailable: Bool
  let localFallbackRetriesRemaining: Int

  init(
    session: TranscriptionSessionRecord?,
    segmentCount: Int?,
    retryCount: Int,
    maxRetries: Int,
    maxLocalFallbackRetries: Int
  ) {
    let now = Date()
    sessionStatus = session?.status.rawValue
    conversationStatus = session?.conversationStatus.rawValue
    finalizationReason = session?.finalizationReason?.rawValue
    hasFinishedAt = session?.finishedAt != nil
    hasFinalizationStartedAt = session?.finalizationStartedAt != nil
    hasFinalizationCompletedAt = session?.finalizationCompletedAt != nil
    hasInputDeviceName = session?.inputDeviceName?.isEmpty == false
    hasLocalSegments = segmentCount.map { $0 > 0 }
    sessionAgeSeconds = session.map { max(0, Int(now.timeIntervalSince($0.createdAt).rounded())) }
    if let startedAt = session?.startedAt {
      let finishedAt = session?.finishedAt ?? now
      sessionDurationSeconds = max(0, Int(finishedAt.timeIntervalSince(startedAt).rounded()))
    } else {
      sessionDurationSeconds = nil
    }
    localFallbackAvailable =
      session?.finalizationStrategy == .cloudReconcile
      && (segmentCount ?? 0) > 0
      && retryCount >= maxRetries
    localFallbackRetriesRemaining = max(0, maxRetries + maxLocalFallbackRetries - retryCount)
  }
}
