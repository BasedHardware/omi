import Foundation

extension TaskAssistant {
  func processFrame(_ frame: CapturedFrame) async {
    let screenTaskEnabled = await ScreenTaskFeature.isEnabled
    await DesktopLogPrivacy.$suppressContent.withValue(screenTaskEnabled) {
      await processFrame(frame, screenTaskEnabled: screenTaskEnabled)
    }
  }

  private func processFrame(_ frame: CapturedFrame, screenTaskEnabled: Bool) async {
    let enabled = await isEnabled
    guard enabled else {
      log("Task: Skipping analysis (disabled)")
      return
    }

    log("Task: Analyzing frame from \(frame.appName)...")
    do {
      let authorization = screenTaskEnabled ? screenTaskFrameOwners.authorization(for: frame) : nil
      let extraction: ScreenTaskExtraction
      if screenTaskEnabled {
        extraction = try await extractScreenTasks(frame: frame, authorization: authorization)
      } else {
        let (results, searchCount) = try await extractTaskSingleStage(from: frame.jpegData, appName: frame.appName)
        extraction = ScreenTaskExtraction(results: results, searchCount: searchCount)
      }
      let results = extraction.results
      let searchCount = extraction.searchCount
      if screenTaskEnabled {
        guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      }
      guard !results.isEmpty else {
        log("Task: Analysis returned no results")
        return
      }

      let extractedCount = results.filter { $0.hasNewTask }.count
      if screenTaskEnabled {
        ScreenTaskLogging.completed(results: results.count, extracted: extractedCount, searches: searchCount)
      } else {
        log(
          "Task: Analysis complete - results: \(results.count) (extracted: \(extractedCount)), context: \(results.first?.contextSummary ?? ""), searches: \(searchCount)"
        )

      }

      await ScreenTaskDelivery.deliver(extraction) { result in
        if screenTaskEnabled {
          guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return false }
        }
        return await handleResultWithScreenshot(
          result, screenshotId: frame.screenshotId, appName: frame.appName, windowTitle: frame.windowTitle,
          recordExtractionEvent: extraction.admission?.auditSample != true
        ) { type, data in
          let boxed = TaskAssistantEventPayloadBox(data)
          Task { @MainActor in
            if screenTaskEnabled {
              guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
            }
            AssistantCoordinator.shared.sendEvent(type: type, data: boxed.value)
          }
        }
      } recordAudit: { event in
        guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
        PostHogManager.shared.taskExtracted(
          taskCount: event.taskCount, gateOutcome: event.gateOutcome, auditSample: event.auditSample,
          candidateCount: event.candidateCount)
      }
    } catch {
      if screenTaskEnabled { ScreenTaskLogging.failed() } else { logError("Task extraction error", error: error) }
    }
  }

  func extractScreenTasks(frame: CapturedFrame, authorization: RuntimeOwnerAuthorizationSnapshot?) async throws
    -> ScreenTaskExtraction
  {
    guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw CancellationError()
    }
    var admission: ScreenTaskAdmission?
    do {
      let ocr = try await RewindOCRService.shared.extractTextWithBounds(from: frame.jpegData)
      let lines = ScreenTaskDedupe.lines(ocr: ocr, app: frame.appName)
      let key = "\(authorization.ownerID):\(authorization.authorizationGeneration):\(frame.appName)"
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw CancellationError() }
      if screenTaskDedupe.shouldSkip(key: key, lines: lines, now: frame.captureTime) {
        return ScreenTaskExtraction(results: [], searchCount: 0)
      }
      try await ScreenTaskFeature.enforceQuota()
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw CancellationError() }
      let text = String(ocr.fullText.prefix(12000))
      let keywords = await executeKeywordSearch(query: String(text.prefix(3000)))
      let context = ScreenTaskContext.select(keywords: keywords, query: text)
      let profile = await AIUserProfileService.shared.getLatestProfile()?.profileText ?? ""
      let gate: ScreenTaskAdmission
      do {
        if ocr.fullText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || ocr.fullText.count > 12000 {
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "screen_task_gate", from: "other", to: "none", reason: "other", outcome: .recovered)
          // Truncation could hide a new request. Missing/oversized OCR never rejects a frame.
          gate = ScreenTaskAdmission(shouldExtract: true, gateOutcome: "fail_open", auditSample: false)
        } else {
          gate = try await APIClient.shared.screenTaskGate(
            ocrText: text, app: frame.appName,
            profile: String(profile.prefix(1024)),
            tasks: Array(context.prefix(4)).map { "[\($0.status)] \($0.description.prefix(512))" },
            authorization: authorization)
        }
      } catch {
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization), !Task.isCancelled else {
          throw CancellationError()
        }
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "screen_task_gate", from: "other", to: "none", reason: "other", outcome: .recovered)
        gate = ScreenTaskAdmission(shouldExtract: true, gateOutcome: "fail_open", auditSample: false)
      }
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization), !Task.isCancelled else {
        throw CancellationError()
      }
      admission = gate
      guard gate.shouldExtract else {
        screenTaskDedupe.record(key: key, lines: lines, now: frame.captureTime)
        return ScreenTaskExtraction(results: [], searchCount: 1)
      }
      let formatter = DateFormatter()
      formatter.locale = Locale(identifier: "en_US_POSIX")
      formatter.dateFormat = "yyyy-MM-dd"  // omi-ux-allow: date-format-string -- Fixed extractor wire date, never user-facing UI.
      let today = formatter.string(from: Date())
      let body = try ScreenTaskPrompt.request(
        jpeg: frame.jpegData, app: frame.appName, profile: profile, tasks: context, today: today)
      let response = try await APIClient.shared.extractScreenTask(
        body: body, authorization: authorization,
        gateOutcome: gate.gateOutcome, auditSample: gate.auditSample)
      let results = try JSONDecoder().decode(ScreenTaskResponse.self, from: Data(response.utf8)).results(
        app: frame.appName, context: context, today: today)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw CancellationError() }
      screenTaskDedupe.record(key: key, lines: lines, now: frame.captureTime)
      return ScreenTaskExtraction(results: results, searchCount: 1, admission: gate)
    } catch {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization), !Task.isCancelled else {
        throw CancellationError()
      }
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "screen_task_extraction", from: "other", to: "other", reason: "other", outcome: .degraded)
      let (results, searchCount) = try await extractTaskSingleStage(
        from: frame.jpegData, appName: frame.appName, authorization: authorization)
      return ScreenTaskExtraction(results: results, searchCount: searchCount, admission: admission)
    }
  }
}
