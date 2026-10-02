import Foundation

extension TaskAssistant {
  func handleResult(_ result: AssistantResult, sendEvent: @escaping @Sendable (String, [String: Any]) -> Void) async {
    // analyze(frame:) only queues immutable bound frames and returns nil. Delivery
    // runs in processFrame; an unbound protocol result must never acquire the current owner.
  }

  /// Handle result with screenshot ID for SQLite storage
  @discardableResult
  func handleResultWithScreenshot(
    _ taskResult: TaskExtractionResult,
    screenshotId: Int64?,
    appName: String,
    windowTitle: String? = nil,
    recordExtractionEvent: Bool = true,
    authorization: RuntimeOwnerAuthorizationSnapshot?,
    provenance: ScreenTaskDeliveryProvenance = ScreenTaskDeliveryProvenance(extractor: "legacy"),
    sendEvent: @escaping (String, [String: Any]) -> Void
  ) async -> ScreenTaskDeliveryCounts {
    guard let authorization else { return .failure }
    let mutation = Self.mutationAuthorization(authorization)
    guard (try? mutation.require()) != nil else { return .failure }
    // Save observation for every result (fire-and-forget)
    let observationApp = taskResult.task?.sourceApp ?? appName
    let observation = ObservationRecord(
      screenshotId: screenshotId,
      appName: observationApp,
      contextSummary: taskResult.contextSummary,
      currentActivity: taskResult.currentActivity,
      hasTask: taskResult.hasNewTask,
      taskTitle: taskResult.task?.title,
      sourceCategory: taskResult.task?.sourceCategory,
      sourceSubcategory: taskResult.task?.sourceSubcategory,
      createdAt: Date()
    )
    let observationAuthorizationSnapshot = authorization
    Task {
      do {
        try await ActionItemStorage.shared.insertObservation(
          observation,
          authorization: mutation
        )
      } catch {
        if RuntimeOwnerIdentity.isAuthorizationCurrent(observationAuthorizationSnapshot) {
          logError("Task: Failed to insert observation", error: error)
        }
      }
    }

    guard taskResult.hasNewTask, let task = taskResult.task else {
      return ScreenTaskDeliveryCounts(policyRejected: taskResult.hasNewTask ? 1 : 0)
    }

    guard
      let threshold = try? await ScreenTaskAuthorizedOperation.run(
        authorization: mutation, operation: { await self.minConfidence })
    else { return .failure }
    guard (try? mutation.require()) != nil else { return .failure }
    let confidencePercent = Int(task.confidence * 100)

    guard task.confidence >= threshold else {
      log("Task: [\(confidencePercent)% < \(Int(threshold * 100))%] Filtered: \"\(task.title)\"")
      return ScreenTaskDeliveryCounts(policyRejected: taskResult.hasNewTask ? 1 : 0)
    }

    log("Task: [\(confidencePercent)% conf.] \"\(task.title)\"")

    previousTasks.insert(task, at: 0)
    if previousTasks.count > maxPreviousTasks {
      previousTasks.removeLast()
    }

    // Persist a hidden outbox row before any backend work.
    let extractionRecord = await saveTaskToSQLite(
      task: task,
      screenshotId: screenshotId,
      contextSummary: taskResult.contextSummary,
      windowTitle: windowTitle,
      provenance: provenance,
      authorization: mutation
    )

    guard (try? mutation.require()) != nil else { return .failure }
    var counts = await syncTaskToBackend(
      task: task,
      taskResult: taskResult,
      localRecord: extractionRecord,
      windowTitle: windowTitle,
      authorization: authorization
    )

    counts.outboxSaved = extractionRecord == nil ? 0 : 1
    guard (try? mutation.require()) != nil else { return .failure }
    if recordExtractionEvent, counts.pendingDelivered > 0 {
      await MainActor.run {
        if (try? mutation.require()) != nil { AnalyticsManager.shared.taskExtracted(taskCount: 1) }
      }
    }

    guard (try? mutation.require()) != nil else { return .failure }
    sendEvent(
      "taskExtracted",
      [
        "assistant": identifier,
        "task": task.toDictionary(),
        "contextSummary": taskResult.contextSummary,
      ])
    return counts
  }

  nonisolated static func mutationAuthorization(_ authorization: RuntimeOwnerAuthorizationSnapshot)
    -> LocalMutationAuthorization
  {
    let workValidator = ScreenTaskWorkAuthority.validate
    return LocalMutationAuthorization {
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
        && RewindDatabase.currentUserId == authorization.ownerID
        && {
          do {
            try workValidator?()
            return true
          } catch { return false }
        }()
    }
  }

  /// Generate embedding for a newly saved staged task and store it
  private func generateEmbeddingForTask(id: Int64, text: String) async {
    do {
      let embedding = try await EmbeddingService.shared.embed(text: text)
      let data = await EmbeddingService.shared.floatsToData(embedding)
      try await StagedTaskStorage.shared.updateEmbedding(id: id, embedding: data)
      await EmbeddingService.shared.addToIndex(source: .staged, id: id, embedding: embedding)
      log("Task: Generated embedding for staged task \(id)")
    } catch {
      logError("Task: Failed to generate embedding for staged task \(id)", error: error)
    }
  }

  /// Save extracted task to staged_tasks SQLite table
  private func saveTaskToSQLite(
    task: ExtractedTask,
    screenshotId: Int64?,
    contextSummary: String,
    windowTitle: String? = nil,
    provenance: ScreenTaskDeliveryProvenance,
    authorization: LocalMutationAuthorization
  ) async -> StagedTaskRecord? {
    var metadata: [String: Any] = [
      "tags": task.tags,
      "context_summary": contextSummary,
      "source_category": task.sourceCategory,
      "source_subcategory": task.sourceSubcategory,
      "capture_kind": task.captureKind ?? "direct_request",
      "owner": task.owner ?? "unknown",
      "concrete_deliverable": task.concreteDeliverable ?? false,
      "public_broadcast": task.publicBroadcast ?? false,
      "direct_mention": task.directMention ?? false,
      "already_done": task.alreadyDone ?? false,
      "ownership_confidence": task.ownershipConfidence ?? 0.5,
    ]
    provenance.store(in: &metadata)
    if let duplicateOf = task.duplicateOf { metadata["duplicate_of"] = duplicateOf }
    if let refinesTask = task.refinesTask { metadata["refines_task"] = refinesTask }
    if let primaryTag = task.primaryTag {
      metadata["category"] = primaryTag
    }
    if let deadline = task.inferredDeadline {
      metadata["inferred_deadline"] = deadline
    }
    if let windowTitle = windowTitle {
      metadata["window_title"] = windowTitle
    }

    let metadataJson: String?
    if let data = try? JSONSerialization.data(withJSONObject: metadata),
      let json = String(data: data, encoding: .utf8)
    {
      metadataJson = json
    } else {
      metadataJson = nil
    }

    let tagsJson: String?
    if let data = try? JSONEncoder().encode(task.tags),
      let json = String(data: data, encoding: .utf8)
    {
      tagsJson = json
    } else {
      tagsJson = nil
    }

    let dueAt = parseDueDate(from: task.inferredDeadline)

    let record = StagedTaskRecord(
      backendSynced: false,
      description: task.title,
      // The row is born hidden and retryable. Mode resolution may later
      // convert it to legacy staging, but a crash can never expose a local
      // Candidate that canonical authority has not received.
      source: "candidate_outbox",
      priority: task.priority.rawValue,
      category: task.primaryTag,
      tagsJson: tagsJson,
      dueAt: dueAt,
      screenshotId: screenshotId,
      confidence: task.confidence,
      sourceApp: task.sourceApp,
      windowTitle: windowTitle,
      contextSummary: contextSummary,
      metadataJson: metadataJson,
      relevanceScore: nil,
      scoredAt: nil
    )

    do {
      let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(record, authorization: authorization)
      log("Task: Saved retryable capture outbox row (id: \(inserted.id ?? -1))")
      return inserted
    } catch {
      logError("Task: Failed to save to staged_tasks", error: error)
      return nil
    }
  }

  /// Deliver the local outbox row through the mode-owned backend authority.
  func syncTaskToBackend(
    task: ExtractedTask,
    taskResult: TaskExtractionResult,
    localRecord: StagedTaskRecord?,
    windowTitle: String? = nil,
    authorization: RuntimeOwnerAuthorizationSnapshot,
    deferred: Bool = false
  ) async -> ScreenTaskDeliveryCounts {
    let mutation = Self.mutationAuthorization(authorization)
    guard (try? mutation.require()) != nil else { return .failure }
    guard await AccountCutoverOfflineUploadAdmission.allowsUploadOffMainActor() else { return .failure }
    guard let localRecord, let localID = localRecord.id else {
      log("Task: Capture outbox persistence failed; refusing an untracked backend write")
      return .failure
    }
    do {
      let control = try await ScreenTaskAuthorizedOperation.run(authorization: mutation) {
        try await APIClient.shared.getCandidateWorkflowControl(
          expectedOwnerId: authorization.ownerID, authorizationSnapshot: authorization)
      }
      guard let mode = control.workflowMode else {
        log("Task: Workflow control omitted mode; capture remains retryable")
        return .failure
      }

      if mode == .read {
        guard let generation = control.accountGeneration else {
          log("Task: Workflow control omitted generation; capture remains retryable")
          return .failure
        }
        let evidenceVersion = ScreenCandidateAdapter.evidenceVersion(
          for: localRecord.screenshotId
        )
        let decision = ScreenCandidateAdapter.adapt(
          task: task,
          dueAt: parseDueDate(from: task.inferredDeadline),
          localEvidenceID: "screen-\(localRecord.screenshotId ?? localID)",
          deviceID: ClientDeviceService.shared.clientDeviceId,
          evidenceVersion: evidenceVersion
        )
        guard decision.candidate != nil else {
          try await StagedTaskStorage.shared.discardCanonicalOutbox(id: localID, authorization: mutation)
          return ScreenTaskDeliveryCounts(policyRejected: 1)
        }

        // The model's duplicate search is advisory. Repeated screenshots can
        // paraphrase the same visible ask, and canonical exact-description
        // identity will not merge those variants. Resolve delivery in one DB
        // transaction so dismiss-vs-reuse and first-writer dual-create cannot
        // mint two Candidates for the same observation burst.
        switch try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
          for: localRecord,
          localOutboxID: localID,
          authorization: mutation
        ) {
        case .adoptedExistingReceipt(let receipt):
          log(
            "Task: Reused canonical capture candidate=\(receipt.candidateID) for semantically equivalent observation"
          )
          return ScreenTaskDeliveryCounts(coalesced: 1)
        case .coalescedIntoDeliveryLeader:
          log(
            "Task: Coalesced equivalent capture into older delivery leader; skipping backend create"
          )
          return ScreenTaskDeliveryCounts(coalesced: 1)
        case .proceedAsDeliveryLeader:
          break
        }
        let delivery = CanonicalScreenCandidateDelivery(
          client: APICanonicalScreenCandidateClient(authorization: authorization)
        )
        guard
          let canonicalState = try await delivery.deliver(
            decision,
            localID: localID,
            deviceID: ClientDeviceService.shared.deviceIdHash,
            accountGeneration: generation
          )
        else { return .failure }
        let canonicalStatus = canonicalState.status
        let canonicalTaskID = canonicalState.taskID
        let completion = try await ScreenTaskReceiptDelivery.complete(
          id: localID,
          candidateID: canonicalState.candidateID,
          status: canonicalStatus.rawValue,
          taskID: canonicalTaskID,
          ownerID: authorization.ownerID,
          deferred: deferred,
          authorization: mutation
        )
        let confidenceBand = TaskIntelligenceConfidenceBand.forCapture(
          confidence: task.confidence,
          explicit: task.captureKind == "explicit_command"
        )
        let capturedAttribution = TaskIntelligenceAttributionEvent.candidateCaptured(
          candidateID: canonicalState.candidateID,
          confidenceBand: confidenceBand
        )
        let resolvedAttribution: TaskIntelligenceAttributionEvent? = {
          if canonicalStatus == .accepted, let canonicalTaskID {
            return .candidateResolved(
              candidateID: canonicalState.candidateID,
              taskID: canonicalTaskID,
              resolutionCode: .accepted
            )
          }
          if canonicalStatus == .rejected {
            return .candidateResolved(
              candidateID: canonicalState.candidateID,
              taskID: nil,
              resolutionCode: .rejected
            )
          }
          if canonicalStatus == .expired {
            return .candidateResolved(
              candidateID: canonicalState.candidateID,
              taskID: nil,
              resolutionCode: .expired
            )
          }
          return nil
        }()
        await MainActor.run {
          guard (try? mutation.require()) != nil else { return }
          AnalyticsManager.shared.taskIntelligenceAttribution(capturedAttribution)
          if let resolvedAttribution {
            AnalyticsManager.shared.taskIntelligenceAttribution(resolvedAttribution)
          }
        }
        log(
          "Task: Canonical capture reconciled candidate=\(canonicalState.candidateID) outcome=\(decision.outcome.rawValue)"
        )
        return ScreenTaskDeliveryCounts(pendingDelivered: completion?.status == "pending" ? 1 : 0)
      }

      // I1: screen capture proposes, it never creates. `.read` above is the only
      // path that persists anything, and it persists a pending Candidate. Any
      // other mode — including the `.off` the control endpoint returns when its
      // Firestore read fails — leaves the capture in the outbox to retry. A
      // backend hiccup must never be the reason a task appears in the list.
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "task_workflow",
        from: "workflow_control",
        to: "capture_deferred",
        reason: "other",
        outcome: .degraded
      )
      log("Task: Non-canonical workflow mode \(mode); capture deferred and remains retryable")
      return ScreenTaskDeliveryCounts()
    } catch {
      await CandidateOutboxRetryPolicy.handleDeliveryFailure(error, localID: localID, authorization: mutation)
      return .failure
    }
  }

}
