import Foundation

extension TaskAssistant {
  func processFrame(_ frame: CapturedFrame) async {
    let enabled = await isEnabled
    guard enabled else {
      log("Task: Skipping analysis (disabled)")
      return
    }

    log("Task: Analyzing frame from \(frame.appName)...")
    do {
      let screenTaskEnabled = await ScreenTaskFeature.isEnabled
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
      let (results, searchCount) =
        try await screenTaskEnabled
        ? extractScreenTasks(frame: frame, authorization: authorization)
        : extractTaskSingleStage(from: frame.jpegData, appName: frame.appName)
      if screenTaskEnabled {
        guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      }
      guard !results.isEmpty else {
        log("Task: Analysis returned no results")
        return
      }

      let extractedCount = results.filter { $0.hasNewTask }.count
      log(
        "Task: Analysis complete - results: \(results.count) (extracted: \(extractedCount)), context: \(results.first?.contextSummary ?? ""), searches: \(searchCount)"
      )

      for result in results {
        await handleResultWithScreenshot(
          result, screenshotId: frame.screenshotId, appName: frame.appName, windowTitle: frame.windowTitle
        ) { type, data in
          let boxed = TaskAssistantEventPayloadBox(data)
          Task { @MainActor in
            if screenTaskEnabled {
              guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
            }
            AssistantCoordinator.shared.sendEvent(type: type, data: boxed.value)
          }
        }
      }
    } catch {
      logError("Task extraction error", error: error)
    }
  }

  func extractScreenTasks(frame: CapturedFrame, authorization: RuntimeOwnerAuthorizationSnapshot?) async throws -> (
    [TaskExtractionResult], Int
  ) {
    guard let authorization else { throw CancellationError() }
    do {
      try await GeminiClient.enforceManagedProactivity()
      let ocr = try await RewindOCRService.shared.extractTextWithBounds(from: frame.jpegData)
      let lines = ScreenTaskDedupe.lines(ocr: ocr, app: frame.appName)
      let key = "\(authorization.ownerID):\(authorization.authorizationGeneration):\(frame.appName)"
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw CancellationError() }
      if screenTaskDedupe.shouldSkip(key: key, lines: lines, now: frame.captureTime) { return ([], 0) }
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
      guard gate.shouldExtract else {
        screenTaskDedupe.record(key: key, lines: lines, now: frame.captureTime)
        return ([], 1)
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
      if gate.auditSample {
        await MainActor.run {
          // Audit observations do not count as accepted/staged user tasks. The existing
          // Task Extracted event carries bounded candidate count, including zero.
          PostHogManager.shared.taskExtracted(
            taskCount: 0, gateOutcome: "rejected", auditSample: true,
            candidateCount: results.filter { $0.hasNewTask }.count)
        }
      }
      screenTaskDedupe.record(key: key, lines: lines, now: frame.captureTime)
      return (results, 1)
    } catch {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization), !Task.isCancelled else {
        throw CancellationError()
      }
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "screen_task_extraction", from: "other", to: "other", reason: "other", outcome: .degraded)
      return try await extractTaskSingleStage(
        from: frame.jpegData, appName: frame.appName, authorization: authorization)
    }
  }
}
