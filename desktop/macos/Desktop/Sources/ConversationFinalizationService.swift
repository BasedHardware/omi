import Foundation

actor ConversationFinalizationService {
  static let shared = ConversationFinalizationService()

  private let maxRetries = 5
  private let maxLocalFallbackRetries = 3
  private var apiClient = APIClient.shared
  private var meetingCompletionNotificationTask: Task<Void, Never>?
  private var pendingMeetingCompletionConversationIDs = Set<String>()
  private var pendingFinalizationProjectionPolls = Set<String>()
  private var pendingScreenEvidenceRetries = Set<String>()
  private var localProjectionHooks: LocalProjectionTestHooks?
  private var isNetworkReachable: @Sendable () async -> Bool =
    ConversationFinalizationService.systemNetworkReachability
  private var clock: @Sendable () -> Date = { Date() }
  private var screenEvidencePass = MeetingScreenEvidencePass.production
  private var isDeferredForOffline = false

  private static let systemNetworkReachability: @Sendable () async -> Bool = {
    await MainActor.run { NetworkReachability.shared.isOnline }
  }

  private init() {}

  deinit {
    meetingCompletionNotificationTask?.cancel()
  }

  func setAPIClientForTesting(_ client: APIClient?) {
    apiClient = client ?? APIClient.shared
  }

  func setLocalProjectionHooksForTesting(_ hooks: LocalProjectionTestHooks?) {
    localProjectionHooks = hooks
  }

  func setNetworkReachabilityForTesting(_ probe: (@Sendable () async -> Bool)?) {
    isNetworkReachable = probe ?? Self.systemNetworkReachability
    isDeferredForOffline = false
  }

  func setClockForTesting(_ clock: (@Sendable () -> Date)?) {
    self.clock = clock ?? { Date() }
  }

  func setScreenEvidencePassForTesting(_ pass: MeetingScreenEvidencePass?) {
    screenEvidencePass = pass ?? .production
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

      guard !sessionsById.isEmpty else { return }
      // Every finalization path needs the backend. Attempting while offline only burns budget and
      // leaves the row looking broken, so wait for a network path; the backoff clock keeps running.
      guard await isNetworkReachable() else {
        if !isDeferredForOffline {
          isDeferredForOffline = true
          log("ConversationFinalization: Offline; deferring \(sessionsById.count) pending sessions")
        }
        return
      }
      if isDeferredForOffline {
        isDeferredForOffline = false
        log("ConversationFinalization: Network available; resuming pending finalizations")
      }
      log(
        "ConversationFinalization: Recovering \(sessionsById.count) pending sessions (\(exhaustedLocalFallbackSessions.count) exhausted cloud sessions have local fallback data)"
      )
      let exhaustedLocalFallbackIds = Set(exhaustedLocalFallbackSessions.compactMap(\.id))
      let recoveryTime = clock()
      for session in sessionsById
      where Self.isDueForRecovery(session, now: recoveryTime, maxRetries: maxRetries) {
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

  /// Unfinished work is always due. Failed sessions wait out their backoff, except exhausted cloud
  /// sessions, which get their bounded local-fallback attempts on the next tick.
  static func isDueForRecovery(_ session: TranscriptionSessionRecord, now: Date, maxRetries: Int) -> Bool {
    guard session.status == .failed else { return true }
    if session.isReadyForRetry(now: now) {
      return true
    }
    return session.effectiveFinalizationStrategy == .cloudReconcile && session.retryCount >= maxRetries
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
      let outcome = try await resolveExhaustedCloudReconciliation(session: latestSession, sessionId: sessionId)
      guard outcome.handled else {
        throw TranscriptionStorageError.invalidState("Exhausted cloud session has no local fallback")
      }
      await postMeetingCompletionIfReady(
        session: latestSession,
        reason: .retry,
        meetingTreatmentEligible: outcome.meetingTreatmentEligible
      )
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
      await storeMeetingContextIfEnabled(for: session)
      guard try await TranscriptionStorage.shared.markSessionUploading(id: sessionId) else {
        return
      }
      let meetingTreatmentEligible: Bool?
      switch strategy {
      case .localSegments:
        if session.conversationRole == .meeting {
          // `/from-segments` writes the notes synchronously, so the OCR flush must precede it.
          _ = await screenEvidencePass.beforeNotes(
            captureInterval: Self.captureInterval(of: session), conversationID: nil, fetchSelectionWindow: nil)
        }
        meetingTreatmentEligible = try await uploadLocalSegments(sessionId: sessionId)
      case .cloudReconcile:
        guard let latestSession = try await TranscriptionStorage.shared.getSession(id: sessionId) else {
          throw TranscriptionStorageError.sessionNotFound
        }
        meetingTreatmentEligible = try await finalizeCloudSession(
          session: latestSession,
          allowForceProcess: allowCloudForceProcess
        )
      }
      // Meeting provenance is persisted on the recording session, while the
      // finalization reason only describes why this particular attempt ended.
      // A max-duration split must not announce a meeting fragment as ready;
      // explicit stop and detector-end completions may wake Chat after the
      // backend/local reconciliation has reached completed.
      await postMeetingCompletionIfReady(
        session: session,
        reason: reason,
        meetingTreatmentEligible: meetingTreatmentEligible
      )
    } catch {
      await markRetryableFailure(sessionId: sessionId, error: error)
    }
  }

  private func storeMeetingContextIfEnabled(for session: TranscriptionSessionRecord) async {
    guard session.conversationRole == .meeting else { return }
    let enabled = await MainActor.run {
      (
        systemCalendar: SystemCalendarMeetingContextFeature.isEnabled,
        onDeviceIdentity: OnDeviceMeetingIdentityFeature.isEnabled
      )
    }
    guard enabled.systemCalendar || enabled.onDeviceIdentity else { return }
    let end = max(session.finishedAt ?? Date(), session.startedAt.addingTimeInterval(1))
    let interval = DateInterval(start: session.startedAt, end: end)

    // This precedes conversation creation/force-processing so the backend overlap resolver can
    // see the row. Both sources share one short ceiling, preserving fail-open finalization on
    // slow local storage, Calendar, or backend I/O.
    await withTaskGroup(of: Void.self) { group in
      group.addTask {
        await withTaskGroup(of: Void.self) { syncGroup in
          if enabled.systemCalendar {
            syncGroup.addTask {
              await SystemCalendarMeetingContextService.shared.syncAuthorizedEvents(overlapping: interval)
            }
          }
          if enabled.onDeviceIdentity {
            syncGroup.addTask {
              await OnDeviceMeetingIdentityService.shared.syncIdentity(overlapping: interval)
            }
          }
          await syncGroup.waitForAll()
        }
      }
      group.addTask {
        try? await Task.sleep(for: .seconds(2))
      }
      _ = await group.next()
      group.cancelAll()
    }
  }

  private func defaultStrategy(for session: TranscriptionSessionRecord) -> TranscriptionFinalizationStrategy {
    if session.backendId?.isEmpty == false {
      return .cloudReconcile
    }
    return session.source == ConversationSource.desktop.rawValue ? .localSegments : .cloudReconcile
  }

  private func uploadLocalSegments(sessionId: Int64, allowBackendIdOverride: Bool = false) async throws -> Bool {
    guard let bundle = try await TranscriptionStorage.shared.getSessionWithSegments(id: sessionId) else {
      throw TranscriptionStorageError.sessionNotFound
    }
    guard !bundle.segments.isEmpty else {
      log("ConversationFinalization: Deleting empty local session \(sessionId)")
      try await TranscriptionStorage.shared.deleteSession(id: sessionId)
      return false
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
        last.person_id == upload.person_id
      {
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
    let clientProcessing = await resolveClientProcessing(
      sessionId: sessionId,
      uploadSegments: uploadSegments,
      startedAt: bundle.session.startedAt
    )
    let captureEvidence: APIClient.CaptureEvidenceLineage?
    if ProcessInfo.processInfo.environment["CAPTURE_EVIDENCE_V1_DARK_WRITE"] == "1" {
      let units = bundle.segments.compactMap { segment -> APIClient.CaptureEvidenceLineage.Unit? in
        guard let id = segment.id, segment.startTime.isFinite, segment.endTime.isFinite,
          segment.startTime >= 0, segment.endTime > segment.startTime
        else { return nil }
        return .init(
          id: String(id),
          startMs: Int64((segment.startTime * 1000).rounded()),
          endMs: Int64((segment.endTime * 1000).rounded()))
      }
      let root = Self.localClientConversationId(session: bundle.session, sessionId: sessionId)
      let complete = units.count == bundle.segments.count && units.count <= 64
      captureEvidence = .init(
        version: 1, capability: "stable_artifact", captureRoot: root,
        clockDomain: "desktop_session_ms", lineage: complete ? "complete" : "incomplete",
        units: complete ? units : [])
    } else {
      captureEvidence = nil
    }
    let request = APIClient.CreateConversationFromSegmentsRequest(
      transcript_segments: uploadSegments,
      source: bundle.session.source,
      started_at: iso.string(from: bundle.session.startedAt),
      finished_at: bundle.session.finishedAt.map { iso.string(from: $0) },
      language: bundle.session.language,
      client_conversation_id: Self.localClientConversationId(session: bundle.session, sessionId: sessionId),
      conversation_role: bundle.session.conversationRole.rawValue,
      conversation_finalization_reason: bundle.session.finalizationReason?.rawValue,
      client_processing: clientProcessing,
      captureEvidence: captureEvidence
    )
    let response = try await apiClient.createConversationFromSegments(request)
    let status = LocalConversationStatus(rawValue: response.status) ?? .processing
    let completed = try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId,
      backendId: response.id,
      conversationStatus: status,
      allowBackendIdOverride: allowBackendIdOverride
    )
    guard completed else {
      if let latest = try await TranscriptionStorage.shared.getSession(id: sessionId),
        latest.status == .completed,
        latest.backendSynced
      {
        return response.meetingTreatmentEligible
      }
      throw TranscriptionStorageError.invalidState(
        "from-segments returned \(response.id) but local completion was rejected"
      )
    }
    let hydrated = await hydrateUploadedLocalConversation(id: response.id)
    if bundle.session.conversationRole == .meeting, let hydrated {
      // Notes are already written by `/from-segments`; adjudicate now so the screenshots exist on
      // every surface before anyone opens the note. Nothing waits for it.
      let pass = screenEvidencePass
      Task { _ = await pass.afterCreation(conversation: hydrated) }
    }
    log("ConversationFinalization: Uploaded local session \(sessionId) -> backend conversation \(response.id)")
    return response.meetingTreatmentEligible
  }

  private func resolveClientProcessing(
    sessionId: Int64,
    uploadSegments: [APIClient.UploadSegment],
    startedAt: Date
  ) async -> Data? {
    let flagEnabled = localProjectionHooks?.flagEnabled ?? FreeTierLocalProcessingFlag.isEnabled()
    let entitlement: SubscriptionEntitlementDecision
    if let pinned = localProjectionHooks?.entitlement {
      entitlement = pinned
    } else {
      entitlement = await SubscriptionEntitlementService.shared.decisionForManagedProactivity()
    }
    let thermalState = localProjectionHooks?.thermalState ?? ProcessInfo.processInfo.thermalState
    let decision = LocalProjectionFinalization.decision(
      flagEnabled: flagEnabled,
      entitlement: entitlement,
      thermalState: thermalState
    )
    guard decision != .skip else { return nil }

    let summarizer: (any ConversationSummarizing)?
    if let hooked = localProjectionHooks?.summarizer {
      summarizer = hooked
    } else {
      summarizer = await makeProductionSummarizer()
    }
    return await LocalProjectionFinalization.projection(
      decision: decision,
      sessionId: sessionId,
      segments: uploadSegments.map(\.hashSegment),
      startedAt: startedAt,
      summarizer: summarizer
    )
  }

  private func makeProductionSummarizer() async -> ConversationChunkSummarizer? {
    guard let queue = await RewindDatabase.shared.getDatabaseQueue() else { return nil }
    return ConversationChunkSummarizer(
      runtime: LocalInferenceRuntime.makeDefault(),
      store: GRDBLocalProjectionStore(queue: queue)
    )
  }

  @discardableResult
  private func hydrateUploadedLocalConversation(id conversationId: String) async -> ServerConversation? {
    do {
      let conversation = try await apiClient.getConversation(id: conversationId)
      _ = try await TranscriptionStorage.shared.syncServerConversation(conversation)
      log("ConversationFinalization: Hydrated uploaded local conversation \(conversationId)")
      return conversation
    } catch {
      logError(
        "ConversationFinalization: Failed to hydrate uploaded local conversation \(conversationId)",
        error: error
      )
      return nil
    }
  }

  static func captureInterval(of session: TranscriptionSessionRecord) -> DateInterval {
    let end = max(session.finishedAt ?? Date(), session.startedAt.addingTimeInterval(1))
    return DateInterval(start: session.startedAt, end: end)
  }

  /// Ask the backend to process one conversation, gathering the meeting's screen evidence first so
  /// the notes it writes can use it. Bounded and fail-open (`MeetingScreenEvidencePass`).
  private func finalizeBackendConversation(
    id conversationId: String,
    session: TranscriptionSessionRecord
  ) async throws -> ServerConversation {
    guard session.conversationRole == .meeting else {
      return try await apiClient.finalizeConversation(id: conversationId)
    }
    let client = apiClient
    let before = await screenEvidencePass.beforeNotes(
      captureInterval: Self.captureInterval(of: session),
      conversationID: conversationId,
      fetchSelectionWindow: {
        try await MeetingScreenEvidencePass.serverSelectionWindow(conversationID: conversationId, client: client)
      })
    let conversation = try await apiClient.finalizeConversation(id: conversationId)
    if before.needsRetryAfterFinalize {
      retryScreenEvidenceAfterFinalize(conversationID: conversation.id)
    }
    return conversation
  }

  /// Adjudicate again once the backend's finalization is terminal. `/finalize` can answer while the
  /// Cloud Tasks worker is still processing, so the POST response is not the signal: this follows
  /// the same durable finalization projection, on the same schedule, as the meeting-completion
  /// wake. Not awaited — finalization and the wake never wait on screen evidence — and coalesced
  /// per conversation.
  private func retryScreenEvidenceAfterFinalize(conversationID: String) {
    guard pendingScreenEvidenceRetries.insert(conversationID).inserted else { return }
    let pass = screenEvidencePass
    let client = apiClient
    Task { [weak self] in
      if await Self.awaitTerminalFinalization(conversationID: conversationID, client: client) {
        _ = await pass.afterFinalize(
          conversationID: conversationID,
          fetchSelectionWindow: {
            try await MeetingScreenEvidencePass.serverSelectionWindow(conversationID: conversationID, client: client)
          })
      }
      await self?.clearScreenEvidenceRetry(conversationID: conversationID)
    }
  }

  private func clearScreenEvidenceRetry(conversationID: String) {
    pendingScreenEvidenceRetries.remove(conversationID)
  }

  /// Whether the finalization projection reached `completed` within the projection-poll budget.
  /// A missing projection (404) is an inline finalization, already terminal when `/finalize`
  /// returned; `dead_letter` never produced notes worth attaching screenshots to.
  static func awaitTerminalFinalization(conversationID: String, client: APIClient) async -> Bool {
    for delay in finalizationProjectionForegroundDelays + finalizationProjectionBackgroundDelays {
      if delay > 0 {
        try? await Task.sleep(nanoseconds: delay)
      }
      do {
        let status = try await client.getConversationFinalizationStatus(id: conversationID)
        if status.status == "completed" { return true }
        if status.status == "dead_letter" { return false }
      } catch APIError.httpError(statusCode: 404, detail: _) {
        return true
      } catch {
        continue
      }
    }
    return false
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
  ) async throws -> Bool? {
    guard let sessionId = session.id else { return nil }

    if let backendId = session.backendId, !backendId.isEmpty {
      if let clientConversationId = session.clientConversationId,
        !clientConversationId.isEmpty,
        backendId != clientConversationId
      {
        log(
          "ConversationFinalization: Rejecting mismatched backend binding for session \(sessionId); resolving exact client recording id instead"
        )
        if try await completeCloudConversation(
          id: clientConversationId,
          session: session,
          allowForceProcess: allowForceProcess,
          allowBackendIdOverride: true
        ) {
          return nil
        }
        throw TranscriptionStorageError.invalidState(
          "Bound backend conversation conflicts with client recording identity")
      }
      let conversation: ServerConversation
      if allowForceProcess {
        conversation = try await finalizeBackendConversation(id: backendId, session: session)
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
        return nil
      }
      throw TranscriptionStorageError.invalidState("Bound backend conversation is not completed")
    }

    if let clientConversationId = session.clientConversationId, !clientConversationId.isEmpty {
      if try await completeCloudConversation(
        id: clientConversationId,
        session: session,
        allowForceProcess: true
      ) {
        return nil
      }
    }

    if allowForceProcess, session.conversationRole == .meeting {
      // The conversation id is unknown until force-process answers, so only the OCR flush can
      // precede it here.
      _ = await screenEvidencePass.beforeNotes(
        captureInterval: Self.captureInterval(of: session), conversationID: nil, fetchSelectionWindow: nil)
    }
    if allowForceProcess, let conversation = try await apiClient.forceProcessConversation() {
      if DesktopConversationMatchPolicy.matchesDesktopConversation(
        startedAt: conversation.startedAt,
        source: conversation.source,
        sessionStartedAt: session.startedAt
      ) {
        if session.conversationRole == .meeting {
          // The id was unknown before force-process, so this is the first chance to adjudicate.
          retryScreenEvidenceAfterFinalize(conversationID: conversation.id)
        }
        let status = LocalConversationStatus(rawValue: conversation.status.rawValue) ?? .processing
        try await TranscriptionStorage.shared.markSessionCompleted(
          id: sessionId,
          backendId: conversation.id,
          conversationStatus: status
        )
        log("ConversationFinalization: Force-processed unbound cloud session \(sessionId) -> \(conversation.id)")
        return nil
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
      if try await completeTimestampMatchedConversation(match, session: session) {
        return nil
      }
    }

    if session.retryCount >= maxRetries - 1 {
      if let clientConversationId = session.clientConversationId, !clientConversationId.isEmpty {
        if try await completeCloudConversation(
          id: clientConversationId,
          session: session,
          allowForceProcess: true
        ) {
          return nil
        }
      }
      let outcome = try await resolveExhaustedCloudReconciliation(session: session, sessionId: sessionId)
      if outcome.handled {
        return outcome.meetingTreatmentEligible
      }
    }

    throw TranscriptionStorageError.invalidState("No matching backend conversation found")
  }

  private func completeTimestampMatchedConversation(
    _ match: ServerConversation,
    session: TranscriptionSessionRecord
  ) async throws -> Bool {
    guard let sessionId = session.id else { return false }
    let conversation: ServerConversation
    if DesktopConversationMatchPolicy.shouldFinalizeTimestampMatchedConversation(status: match.status) {
      conversation = try await finalizeBackendConversation(id: match.id, session: session)
    } else {
      conversation = match
    }

    guard
      DesktopConversationMatchPolicy.canCompleteTimestampMatchedConversation(
        status: conversation.status,
        source: conversation.source
      ), conversation.id == match.id
    else {
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
  ) async throws -> ExhaustedCloudReconciliationOutcome {
    let segmentCount = try await TranscriptionStorage.shared.getSegmentCount(sessionId: sessionId)
    switch Self.cloudReconciliationExhaustionAction(session: session, segmentCount: segmentCount) {
    case .keepRetrying:
      return ExhaustedCloudReconciliationOutcome(handled: false, meetingTreatmentEligible: nil)
    case .uploadLocalSegments:
      log(
        "ConversationFinalization: Cloud reconciliation exhausted for session \(sessionId); uploading \(segmentCount) saved local segments"
      )
      let meetingTreatmentEligible = try await uploadLocalSegments(
        sessionId: sessionId,
        allowBackendIdOverride: session.backendId?.isEmpty == false
      )
      return ExhaustedCloudReconciliationOutcome(
        handled: true,
        meetingTreatmentEligible: meetingTreatmentEligible
      )
    case .discardEmptyDesktopSession:
      log("ConversationFinalization: Deleting empty unreconciled desktop session \(sessionId)")
      try await TranscriptionStorage.shared.deleteSession(id: sessionId)
      return ExhaustedCloudReconciliationOutcome(handled: true, meetingTreatmentEligible: false)
    case .reportFailure:
      return ExhaustedCloudReconciliationOutcome(handled: false, meetingTreatmentEligible: nil)
    }
  }

  struct ExhaustedCloudReconciliationOutcome: Equatable {
    let handled: Bool
    let meetingTreatmentEligible: Bool?
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
    session: TranscriptionSessionRecord,
    allowForceProcess: Bool,
    allowBackendIdOverride: Bool = false
  ) async throws -> Bool {
    guard let sessionId = session.id else { return false }
    let conversation: ServerConversation
    do {
      if allowForceProcess {
        conversation = try await finalizeBackendConversation(id: conversationId, session: session)
      } else {
        conversation = try await apiClient.getConversation(id: conversationId)
      }
    } catch APIError.httpError(let statusCode, _) where statusCode == 404 {
      return false
    }

    guard
      DesktopConversationMatchPolicy.canCompleteBoundBackendConversation(
        id: conversation.id,
        boundBackendId: conversationId,
        status: conversation.status,
        source: conversation.source
      )
    else {
      return false
    }

    let status = LocalConversationStatus(rawValue: conversation.status.rawValue) ?? .processing
    try await TranscriptionStorage.shared.markSessionCompleted(
      id: sessionId,
      backendId: conversation.id,
      conversationStatus: status,
      allowBackendIdOverride: allowBackendIdOverride
    )
    log("ConversationFinalization: Reconciled cloud session \(sessionId) by conversation id \(conversation.id)")
    return true
  }

  private func markRetryableFailure(sessionId: Int64, error: Error) async {
    let failureClass = FinalizationFailureClass.classify(error)
    let message = error.localizedDescription
    do {
      let session = try await TranscriptionStorage.shared.getSession(id: sessionId)
      if failureClass == .offline {
        // Release the upload claim without spending budget: no path to the backend says nothing
        // about whether this session can finalize.
        log("ConversationFinalization: Session \(sessionId) attempt failed offline; retry budget unchanged")
        try await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: message)
        return
      }
      let retryCount = (session?.retryCount ?? 0) + 1
      if let session, session.effectiveFinalizationStrategy == .localSegments {
        // The local transcript is the only copy and from-segments is idempotent on
        // client_conversation_id, so there is no exhausted state: keep retrying on the capped backoff.
        if failureClass == .permanent {
          if !session.hasPermanentFinalizationFailure {
            await reportPermanentLocalUploadRejection(session: session, error: error, retryCount: retryCount)
          }
          try await TranscriptionStorage.shared.incrementRetryCount(id: sessionId)
          try await TranscriptionStorage.shared.markSessionFailed(
            id: sessionId,
            error: FinalizationRetryPolicy.permanentFailurePrefix + message
          )
          return
        }
      } else if retryCount >= maxRetries {
        // Retries are exhausted. The in-line reconciliation fallback (resolveExhaustedCloudReconciliation)
        // only runs when the final attempt returns cleanly with no match; when it fails by *throwing*
        // (backend/network error), we land here instead and would abandon the session, dropping any
        // recorded audio/transcript we still hold locally (#9083). Try to finalize from saved local
        // segments first so the recording is not lost.
        if let session {
          do {
            let outcome = try await resolveExhaustedCloudReconciliation(session: session, sessionId: sessionId)
            if outcome.handled {
              log(
                "ConversationFinalization: Recovered exhausted session \(sessionId) from local data after finalize error"
              )
              await postMeetingCompletionIfReady(
                session: session,
                reason: .retry,
                meetingTreatmentEligible: outcome.meetingTreatmentEligible
              )
              return
            }
          } catch {
            logError(
              "ConversationFinalization: Local fallback for exhausted session \(sessionId) failed",
              error: error
            )
          }
        }
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

  /// Reported once per transition into the rejected state; the session stays queued at the
  /// hourly cadence so a backend fix drains it without user action.
  private func reportPermanentLocalUploadRejection(
    session: TranscriptionSessionRecord,
    error: Error,
    retryCount: Int
  ) async {
    let statusLabel: String
    if case APIError.httpError(let statusCode, _) = error {
      statusLabel = String(statusCode)
    } else {
      statusLabel = "unknown"
    }
    logError(
      "ConversationFinalization: Backend rejected local session \(session.id ?? -1) upload (HTTP \(statusLabel)); retrying hourly",
      error: error
    )
    let segmentCount: Int?
    if let sessionId = session.id {
      segmentCount = try? await TranscriptionStorage.shared.getSegmentCount(sessionId: sessionId)
    } else {
      segmentCount = nil
    }
    await AnalyticsManager.shared.conversationReconciliationFailed(
      error: "local_upload_rejected_http_\(statusLabel)",
      reason: "local_segments_rejected",
      source: session.source,
      stage: TranscriptionFinalizationStrategy.localSegments.rawValue,
      retryCount: retryCount,
      hasBackendId: session.backendId?.isEmpty == false,
      hasClientConversationId: session.clientConversationId?.isEmpty == false,
      segmentCount: segmentCount
    )
  }

  static func localClientConversationId(session: TranscriptionSessionRecord, sessionId: Int64) -> String {
    let startedAtMs = Int64((session.startedAt.timeIntervalSince1970 * 1000).rounded())
    return session.clientConversationId ?? "macos-local-\(sessionId)-\(startedAtMs)"
  }

  /// Meeting completion is a post-sync signal. Persisted max-duration
  /// fragments remain silent even when a later crash-recovery attempt uses a
  /// generic `.retry` reason.
  static func shouldNotifyMeetingCompletion(
    session: TranscriptionSessionRecord,
    reason: TranscriptionFinalizationReason
  ) -> Bool {
    guard session.conversationRole == .meeting else { return false }
    let effectiveReason = session.finalizationReason ?? reason
    return effectiveReason == .meetingEnded
      || effectiveReason == .userStop
      || effectiveReason == .crashRecovery
  }

  static func shouldWakeMeetingCompletion(finalizationStatus: ConversationFinalizationStatusResponse) -> Bool {
    finalizationStatus.status == "completed" && finalizationStatus.meetingTreatmentEligible == true
  }

  private func postMeetingCompletionIfReady(
    session: TranscriptionSessionRecord,
    reason: TranscriptionFinalizationReason,
    meetingTreatmentEligible: Bool?
  ) async {
    guard Self.shouldNotifyMeetingCompletion(session: session, reason: reason), let sessionId = session.id else {
      return
    }
    do {
      guard let completed = try await TranscriptionStorage.shared.getSession(id: sessionId),
        completed.status == .completed, completed.backendSynced, completed.backendId?.isEmpty == false
      else { return }
      guard let conversationID = completed.backendId else { return }
      // `meetingTreatmentEligible` is deliberately NOT consulted here. It can originate
      // from the from-segments response, which returns before the backend has finalized
      // the conversation and therefore reports the default `false` rather than a decided
      // verdict. `waitForFinalizationProjectionIfNeeded` reads the authoritative
      // finalization projection, applies the same eligibility rule via
      // `shouldWakeMeetingCompletion`, and fails closed on 404, so it is the only correct
      // gate for the wake decision. The parameter is retained for the callers' plumbing;
      // removing it is follow-up cleanup, not a behavior change.
      guard
        await waitForFinalizationProjectionIfNeeded(
          conversationID: conversationID,
          strategy: completed.finalizationStrategy ?? defaultStrategy(for: completed)
        )
      else { return }
      scheduleMeetingCompletionNotification(conversationID: conversationID)
    } catch {
      logError("ConversationFinalization: Failed to verify meeting completion \(sessionId)", error: error)
    }
  }

  /// Cloud finalization marks the conversation completed before its durable
  /// worker finishes fanout. Do not wake Chat during that gap, and require the
  /// backend's duration/speech policy result before notifying: the first
  /// materialization would consume its debounce window while no meeting intent
  /// exists. A missing legacy job has no authoritative eligibility result and
  /// therefore fails closed.
  private func waitForFinalizationProjectionIfNeeded(
    conversationID: String,
    strategy: TranscriptionFinalizationStrategy
  ) async -> Bool {
    guard strategy == .cloudReconcile else { return true }

    // The first probe is immediate; subsequent bounded delays cover the normal
    // Cloud Tasks admission/worker/fanout path without keeping recovery alive
    // indefinitely. A missing projection is an older inline-finalization path.
    for delay in Self.finalizationProjectionForegroundDelays {
      if delay > 0 {
        try? await Task.sleep(nanoseconds: delay)
      }
      do {
        let status = try await apiClient.getConversationFinalizationStatus(id: conversationID)
        if status.status == "completed" {
          return Self.shouldWakeMeetingCompletion(finalizationStatus: status)
        }
        if status.status == "dead_letter" {
          log("ConversationFinalization: Skipping meeting wake for dead-letter conversation \(conversationID)")
          return false
        }
      } catch APIError.httpError(statusCode: 404, detail: _) {
        // Old inline finalization has no authoritative treatment result. Fail
        // closed so a short meeting cannot bypass the backend policy.
        return false
      } catch {
        // Transient status-read failures should not make a completed meeting
        // permanently silent; continue through the bounded retry window.
      }
    }
    log("ConversationFinalization: Finalization projection not terminal for \(conversationID); deferring Chat wake")
    scheduleFinalizationProjectionPoll(conversationID: conversationID)
    return false
  }

  /// Keep a slow Cloud Tasks fanout from becoming permanently silent after the
  /// foreground debounce has been consumed. Poll only the affected conversation
  /// and coalesce duplicate recovery attempts by conversation id.
  private func scheduleFinalizationProjectionPoll(conversationID: String) {
    guard pendingFinalizationProjectionPolls.insert(conversationID).inserted else { return }
    Task { [weak self] in
      defer {
        Task { [weak self] in
          await self?.clearFinalizationProjectionPoll(conversationID: conversationID)
        }
      }
      for delay in Self.finalizationProjectionBackgroundDelays {
        try? await Task.sleep(nanoseconds: delay)
        guard !Task.isCancelled else { return }
        do {
          let status = try await self?.apiClient.getConversationFinalizationStatus(id: conversationID)
          if let status, status.status == "completed" {
            if Self.shouldWakeMeetingCompletion(finalizationStatus: status) {
              await self?.scheduleMeetingCompletionNotification(conversationID: conversationID)
            }
            return
          }
          if status?.status == "dead_letter" { return }
        } catch APIError.httpError(statusCode: 404, detail: _) {
          return
        } catch {
          continue
        }
      }
    }
  }

  /// The finalization-projection poll schedule, shared by the meeting-completion wake and the
  /// post-finalization screen-evidence retry: an immediate probe plus short foreground delays, then
  /// a slower background tail for a slow Cloud Tasks fanout.
  static let finalizationProjectionForegroundDelays: [UInt64] = [
    0, 250_000_000, 500_000_000, 1_000_000_000, 2_000_000_000, 4_000_000_000,
  ]
  static let finalizationProjectionBackgroundDelays: [UInt64] = [
    5_000_000_000, 15_000_000_000, 30_000_000_000, 60_000_000_000, 120_000_000_000,
  ]

  private func clearFinalizationProjectionPoll(conversationID: String) {
    pendingFinalizationProjectionPolls.remove(conversationID)
  }

  /// Coalesce recovery completions arriving in one burst into one Chat wake.
  /// The materializer fetches all ready receipts, so one notification is enough
  /// and avoids bypassing its foreground debounce once per stale session.
  private func scheduleMeetingCompletionNotification(conversationID: String) {
    pendingMeetingCompletionConversationIDs.insert(conversationID)
    guard meetingCompletionNotificationTask == nil else { return }
    meetingCompletionNotificationTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: 250_000_000)
      guard !Task.isCancelled else { return }
      await self?.flushMeetingCompletionNotifications()
    }
  }

  private func flushMeetingCompletionNotifications() {
    guard !pendingMeetingCompletionConversationIDs.isEmpty else {
      meetingCompletionNotificationTask = nil
      return
    }
    let conversationIDs = Array(pendingMeetingCompletionConversationIDs).sorted()
    pendingMeetingCompletionConversationIDs.removeAll()
    meetingCompletionNotificationTask = nil
    let notification = MeetingCompletionNotification(conversationIDs: conversationIDs)
    Task { @MainActor in
      NotificationCenter.default.post(
        name: .desktopMeetingConversationDidComplete,
        object: notification
      )
    }
  }

  /// The default Apple Silicon path creates its backend conversation through
  /// `/from-segments`, so no cloud-listen `memory_created` event exists. Emit the
  /// same activation contract at that successful, exactly-once storage transition.
  static func localConversationCreatedTelemetry(
    session: TranscriptionSessionRecord,
    conversationId: String
  ) -> ConversationCreatedTelemetry {
    ConversationCreatedTelemetry(session: session, conversationId: conversationId)
  }
}

extension Notification.Name {
  static let desktopMeetingConversationDidComplete = Notification.Name(
    "com.omi.desktop.meetingConversationDidComplete")
}

/// Test seam for S11 attach. Production reads the client flag, S13
/// entitlement cache, live thermal state, and the GRDB summarizer.
struct LocalProjectionTestHooks: Sendable {
  var flagEnabled: Bool
  var entitlement: SubscriptionEntitlementDecision
  var thermalState: ProcessInfo.ThermalState
  var summarizer: (any ConversationSummarizing)?
}

struct ConversationCreatedTelemetry: Equatable, Sendable {
  let conversationId: String
  let source: String
  let durationSeconds: Int?
  let attemptId: String?

  init(session: TranscriptionSessionRecord, conversationId: String) {
    self.conversationId = conversationId
    source = session.source
    durationSeconds = session.finishedAt.map {
      max(0, Int($0.timeIntervalSince(session.startedAt)))
    }
    attemptId = session.captureAttemptId
  }
}

struct MeetingCompletionNotification: Sendable, Equatable {
  let conversationIDs: [String]
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
