import Foundation

struct ScreenTaskPipelineServices: Sendable {
  var validateFrame: @Sendable () throws -> Void
  var validateFeature: @Sendable () throws -> Void
  var quota: @Sendable () async throws -> Void
  var ocr: @Sendable (Data) async throws -> OCRResult
  var retrieve: @Sendable (String) async -> [TaskSearchResult]
  var profile: @Sendable () async -> String
  var gate: @Sendable (String, String, [String]) async throws -> ScreenTaskAdmission
  var extract: @Sendable (Data, ScreenTaskAdmission) async throws -> String
  var legacy: @Sendable () async throws -> ScreenTaskExtraction
  var fallback: @Sendable (String, String) -> Void
  var now: @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
}

/// Production coordinator and offline harness share the same suspension/dispatch boundaries.
actor ScreenTaskPipeline {
  private var dedupe = ScreenTaskDedupe()

  func run(
    frame: CapturedFrame, key: String, services: ScreenTaskPipelineServices,
    metrics: ScreenTaskFrameMetrics
  ) async throws -> ScreenTaskExtraction {
    let requireFeature: @Sendable () throws -> Void = {
      try services.validateFrame()
      try services.validateFeature()
      try Task.checkCancellation()
    }
    do {
      try requireFeature()
      metrics.eligibleFrames = 1
      metrics.featureEnabledAtStart = true
      let start = services.now()
      let ocr = try await services.ocr(frame.jpegData)
      metrics.ocrMS = (services.now() - start) * 1000
      try requireFeature()
      let lines = ScreenTaskDedupe.lines(ocr: ocr, app: frame.appName)
      if dedupe.shouldSkip(key: key, lines: lines, now: services.now()) {
        metrics.outcome = "dedupe_skipped"
        return ScreenTaskExtraction(results: [], searchCount: 0)
      }
      try await services.quota()
      try requireFeature()
      let text = String(ocr.fullText.prefix(12000))
      let retrievalStart = services.now()
      let keywords = await services.retrieve(String(text.prefix(3000)))
      try requireFeature()
      let context = ScreenTaskContext.select(keywords: keywords, query: text)
      let profile = await services.profile()
      metrics.retrievalMS = (services.now() - retrievalStart) * 1000
      try requireFeature()
      let gate: ScreenTaskAdmission
      let gateStart = services.now()
      do {
        if ocr.fullText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || ocr.fullText.count > 12000 {
          metrics.clientBypass = true
          metrics.fallbackReason = "ocr_unusable"
          services.fallback("screen_task_gate", "ocr_unusable")
          gate = ScreenTaskAdmission(
            shouldExtract: true, gateOutcome: "fail_open", auditSample: false, clientBypass: true)
        } else {
          metrics.gateAttempts += 1
          gate = try await ScreenTaskWorkAuthority.$validate.withValue(requireFeature) {
            try await services.gate(
              text, String(profile.prefix(1024)),
              Array(context.prefix(4)).map {
                "[\($0.status)] \($0.description.prefix(512))"
              })
          }
        }
      } catch {
        try services.validateFrame()
        try Task.checkCancellation()
        let malformedGate =
          error is DecodingError
          || (error as? APIError).map {
            if case .invalidResponse = $0 { return true }
            return false
          } == true
        guard let reason = ScreenTaskErrorPolicy.outageReason(error) ?? (malformedGate ? "gate_invalid_response" : nil)
        else { throw error }
        try requireFeature()
        metrics.clientBypass = true
        metrics.fallbackReason = reason
        services.fallback("screen_task_gate", reason)
        gate = ScreenTaskAdmission(
          shouldExtract: true, gateOutcome: "fail_open", auditSample: false, clientBypass: true)
      }
      metrics.gateMS = (services.now() - gateStart) * 1000
      metrics.gateOutcome = gate.gateOutcome
      metrics.auditSample = gate.auditSample
      try requireFeature()
      if !gate.shouldExtract {
        dedupe.record(key: key, lines: lines, now: services.now())
        metrics.outcome = "gate_rejected"
        return ScreenTaskExtraction(results: [], searchCount: 1, admission: gate)
      }
      let formatter = DateFormatter()
      formatter.locale = Locale(identifier: "en_US_POSIX")
      formatter.dateFormat = "yyyy-MM-dd"  // omi-ux-allow: date-format-string -- Extractor wire date.
      let today = formatter.string(from: Date())
      let body = try ScreenTaskPrompt.request(
        jpeg: frame.jpegData, app: frame.appName, profile: profile, tasks: context, today: today)
      try requireFeature()
      let extractionStart = services.now()
      metrics.extractionAttempts += 1
      let textResponse = try await ScreenTaskWorkAuthority.$validate.withValue(requireFeature) {
        try await services.extract(body, gate)
      }
      metrics.extractionMS = (services.now() - extractionStart) * 1000
      try requireFeature()
      let response = try JSONDecoder().decode(ScreenTaskResponse.self, from: Data(textResponse.utf8))
      let results = try response.results(app: frame.appName, context: context, today: today)
      metrics.invalidItems = response.invalidItemCount + response.tasks.count - results.filter { $0.hasNewTask }.count
      dedupe.record(key: key, lines: lines, now: services.now())
      metrics.extractor = "gemini_3_8"
      return ScreenTaskExtraction(results: results, searchCount: 1, admission: gate)
    } catch {
      try services.validateFrame()
      try Task.checkCancellation()
      // Stop means rollback, not a provider fault. Old feature results never reach delivery.
      let stopped =
        (error as? ScreenTaskHTTPFailure)?.stopped == true
        || (error as? ScreenTaskFailure).map {
          if case .stopped = $0 { return true }
          return false
        } == true
      // Extraction outages terminate this frame. No legacy request, observation or dedupe entry.
      guard stopped else {
        if let reason = ScreenTaskErrorPolicy.outageReason(error) {
          metrics.fallbackReason = reason
          throw ScreenTaskFailure.providerOutage
        }
        throw error
      }
      let reason = "dispatch_disabled"
      metrics.fallbackReason = reason
      services.fallback("screen_task_extraction", reason)
      metrics.legacyAttempts += 1
      metrics.pipeline = "legacy"
      let start = services.now()
      var fallback = try await ScreenTaskWorkAuthority.$validate.withValue(services.validateFrame) {
        try await services.legacy()
      }
      try services.validateFrame()
      metrics.extractionMS += (services.now() - start) * 1000
      metrics.extractor = "legacy"
      fallback.extractor = "legacy"
      return fallback
    }
  }
}
