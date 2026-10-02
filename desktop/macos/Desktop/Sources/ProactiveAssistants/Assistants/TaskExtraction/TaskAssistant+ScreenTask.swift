import Foundation

extension TaskAssistant {
  func processFrame(_ frame: CapturedFrame) async {
    let enabled = await ScreenTaskFeature.isEnabled
    let lease = enabled ? ScreenTaskFeature.lease() : nil
    let metrics = ScreenTaskFrameMetrics()
    metrics.featureEnabledAtStart = lease != nil
    if lease == nil { metrics.pipeline = "legacy" }
    await DesktopLogPrivacy.$suppressContent.withValue(await ScreenTaskFeature.isConfigured) {
      do {
        guard await isEnabled else {
          metrics.outcome = "disabled"
          return
        }
        guard let binding = frame.taskBinding else { throw ScreenTaskFailure.ownerRevoked }
        let validateFrame: @Sendable () throws -> Void = {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(binding.authorization) else {
            throw ScreenTaskFailure.ownerRevoked
          }
          guard binding.exclusion.appName == frame.appName,
            RewindCaptureExclusionGeneration.isCurrent(binding.exclusion),
            !ScreenTaskPrivacy.isPrivateWindow(app: frame.appName, title: frame.windowTitle)
          else { throw ScreenTaskFailure.privacyRevoked }
          try Task.checkCancellation()
        }
        try validateFrame()
        metrics.eligibleFrames = 1
        let extraction: ScreenTaskExtraction
        if let lease {
          extraction = try await extractScreenTasks(frame: frame, binding: binding, lease: lease, metrics: metrics)
        } else {
          let extractionStart = ProcessInfo.processInfo.systemUptime
          metrics.legacyAttempts = 1
          extraction = try await ScreenTaskWorkAuthority.$validate.withValue(validateFrame) {
            let (results, searches) = try await extractTaskSingleStage(
              from: frame.jpegData, appName: frame.appName, authorization: binding.authorization)
            return ScreenTaskExtraction(results: results, searchCount: searches, extractor: "legacy")
          }
          metrics.extractionMS = (ProcessInfo.processInfo.systemUptime - extractionStart) * 1000
          metrics.extractor = "legacy"
        }
        try validateFrame()
        let validateDelivery: @Sendable () throws -> Void = {
          try validateFrame()
          if extraction.extractor == "gemini_3_8", let lease, !lease.isCurrent() { throw ScreenTaskFailure.stopped }
        }
        let deliveryStart = ProcessInfo.processInfo.systemUptime
        metrics.counts = try await ScreenTaskWorkAuthority.$validate.withValue(validateDelivery) {
          try validateDelivery()
          return await ScreenTaskDelivery.deliver(extraction) { result in
            guard (try? validateDelivery()) != nil else { return .failure }
            return await handleResultWithScreenshot(
              result, screenshotId: frame.screenshotId, appName: frame.appName, windowTitle: frame.windowTitle,
              recordExtractionEvent: extraction.admission?.auditSample != true,
              authorization: binding.authorization,
              provenance: ScreenTaskDeliveryProvenance(extraction: extraction)
            ) { type, data in
              let boxed = TaskAssistantEventPayloadBox(data)
              Task { @MainActor in
                guard (try? validateDelivery()) != nil else { return }
                AssistantCoordinator.shared.sendEvent(type: type, data: boxed.value)
              }
            }
          } recordAudit: { event in
            guard (try? validateDelivery()) != nil else { return }
            PostHogManager.shared.taskExtracted(
              taskCount: event.taskCount, gateOutcome: event.gateOutcome, auditSample: event.auditSample,
              candidateCount: event.candidateCount, extractor: event.extractor)
          }
        }
        metrics.deliveryMS = (ProcessInfo.processInfo.systemUptime - deliveryStart) * 1000
        if metrics.counts.failed > 0 {
          metrics.outcome = "failed"
          metrics.errorClass = "delivery_failure"
        }
      } catch {
        metrics.finish(error: error)
        if metrics.outcome != "refused" {
          if enabled {
            ScreenTaskLogging.failed()
          } else if ![
            "auth", "plan_or_quota", "backpressure", "http_terminal", "owner_revoked", "privacy_revoked", "cancelled",
          ].contains(metrics.errorClass) {
            logError("Task extraction error", error: error)
          }
        }
      }
    }
    // Exactly one content-free terminal event, including rejects, skips and cancelled/revoked work.
    let properties = metrics.properties(
      captureToTerminalMS: (ProcessInfo.processInfo.systemUptime - frame.capturedUptime) * 1000)
    await MainActor.run {
      PostHogManager.shared.screenTaskFrameTerminal(
        ownerID: frame.taskBinding?.authorization.ownerID, properties: properties)
    }
  }

  func extractScreenTasks(
    frame: CapturedFrame, binding: ScreenTaskFrameBinding, lease: ScreenTaskLease,
    metrics: ScreenTaskFrameMetrics
  ) async throws -> ScreenTaskExtraction {
    let authorization = binding.authorization
    let validateFrame: @Sendable () throws -> Void = {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw ScreenTaskFailure.ownerRevoked }
      guard binding.exclusion.appName == frame.appName, binding.isCurrent(),
        !ScreenTaskPrivacy.isPrivateWindow(app: frame.appName, title: frame.windowTitle)
      else { throw ScreenTaskFailure.privacyRevoked }
      try Task.checkCancellation()
    }
    let services = ScreenTaskPipelineServices(
      validateFrame: validateFrame,
      validateFeature: { guard lease.isCurrent() else { throw ScreenTaskFailure.stopped } },
      quota: {
        try await ScreenTaskFeature.enforceQuota()
        if let failure = ScreenTaskBackpressure.shared.blockedFailure(authorization) { throw failure }
      },
      ocr: { try await RewindOCRService.shared.extractTextWithBounds(from: $0) },
      retrieve: { await self.executeKeywordSearch(query: $0) },
      profile: { await AIUserProfileService.shared.getLatestProfile()?.profileText ?? "" },
      gate: { text, profile, tasks in
        try await APIClient.shared.screenTaskGate(
          ocrText: text, app: frame.appName, profile: profile, tasks: tasks,
          authorization: authorization)
      },
      extract: { body, gate in
        try await APIClient.shared.extractScreenTask(
          body: body, authorization: authorization,
          gateOutcome: gate.gateOutcome, auditSample: gate.auditSample, clientBypass: gate.clientBypass)
      },
      legacy: {
        let (results, searches) = try await self.extractTaskSingleStage(
          from: frame.jpegData, appName: frame.appName, authorization: authorization)
        return ScreenTaskExtraction(results: results, searchCount: searches, extractor: "legacy")
      },
      fallback: { area, reason in
        DesktopDiagnosticsManager.shared.recordFallback(
          area: area,
          from: area == "screen_task_gate" ? "jev" : "gemini_3_8",
          to: area == "screen_task_gate" ? "gemini_3_8" : "legacy",
          reason: reason, outcome: .degraded)
      })
    let key = "\(authorization.ownerID):\(authorization.authorizationGeneration):\(Self.analyzedKey(for: frame))"
    return try await screenTaskPipeline.run(frame: frame, key: key, services: services, metrics: metrics)
  }
}
