#if DEBUG
  import Foundation

  /// Non-production-only, image-independent replay of the context director's model boundary.
  ///
  /// This intentionally stops at the decoded director decision. Durable state, policy gates,
  /// task graduation, and user-visible presentation are outside this replay boundary.
  struct ContextBucketDirectorProbe {
    private final class SendableSchema: @unchecked Sendable {
      let value: [String: Any]

      init(_ value: [String: Any]) {
        self.value = value
      }
    }

    typealias Completion = (
      _ operation: String,
      _ prompt: String,
      _ uncachedPrompt: String?,
      _ imageData: Data?,
      _ jsonSchema: [String: Any],
      _ cacheKey: String?,
      _ maxCompletionTokens: Int,
      _ authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
    ) async throws -> ProactiveLaneResult

    private let completion: Completion
    private let isNonProduction: Bool

    init(client: ProactiveLaneClient = .shared, isNonProduction: Bool? = nil) {
      self.isNonProduction = isNonProduction ?? AppBuild.isNonProduction
      self.completion = {
        operation, prompt, uncachedPrompt, imageData, jsonSchema, cacheKey, maxCompletionTokens,
        authorizationSnapshot in
        let schema = SendableSchema(jsonSchema)
        return try await client.complete(
          operation: operation,
          prompt: prompt,
          uncachedPrompt: uncachedPrompt,
          imageData: imageData,
          jsonSchema: schema.value,
          cacheKey: cacheKey,
          maxCompletionTokens: maxCompletionTokens,
          authorizationSnapshot: authorizationSnapshot)
      }
    }

    init(completion: @escaping Completion, isNonProduction: Bool? = nil) {
      self.isNonProduction = isNonProduction ?? AppBuild.isNonProduction
      self.completion = completion
    }

    /// Replays a synthetic bucket/frame through the exact production prompt and model contract.
    /// The input values are all strings because the automation bridge has a string-valued action
    /// ABI. Tail and fact fields are JSON arrays of strings; tasks are JSON objects with
    /// `description` and nullable `due_at` fields.
    func run(params: [String: String]) async throws -> [String: String] {
      guard isNonProduction else {
        throw ContextBucketDirectorProbeError.nonProductionOnly
      }
      let input = try Input(params: params)
      let snapshot = ContextBucketSnapshot(
        bucketID: input.bucketID,
        versionID: Int64(input.version),
        version: input.version,
        header: input.header,
        frozenRankedSegment: Data(input.frozen.utf8),
        tail: input.tail,
        validatedFacts: input.validatedFacts,
        notifyWorthiness: input.notifyWorthiness,
        visitCount: input.visitCount)
      guard ContextDirectorEligibility.permitsEvaluation(of: snapshot) else {
        return [
          "decision": "silence",
          "title": "",
          "message": "",
          "reasoning": "ineligible_snapshot",
          "bucket_entry_ref_count": "0",
          "fact_ref_count": "0",
          "model": "not_invoked",
          "latency_ms": "0",
        ]
      }
      let frame = CapturedFrame(
        jpegData: Data(),
        appName: input.app,
        windowTitle: input.window,
        frameNumber: 0,
        captureTime: input.capturedAt)
      // A probe with retrieved items replays the *second* director call of a
      // visit exactly as `performRetrievalHop` builds it: lookup instruction in
      // the stable prompt, RETRIEVED CONTEXT section appended to the uncached
      // suffix, and the lookup-enabled schema. Without them it stays the exact
      // first-call replay it always was.
      let retrievedSection =
        input.retrieved.isEmpty
        ? nil
        : ContextDirectorRetrievalHop.promptSection(
          query: input.lookupQuery, items: input.retrieved)
      let allowLookup = retrievedSection != nil
      let prompt = ContextProactivityPromptBuilder.directorStablePrompt(
        snapshot: snapshot, allowLookup: allowLookup)
      let volatilePrompt = ContextProactivityPromptBuilder.directorVolatilePrompt(
        tasks: input.tasks, frame: frame, recentDeliveries: input.recentDeliveries,
        visitCount: input.visitCount)
      let uncachedPrompt = retrievedSection.map { volatilePrompt + "\n\n" + $0 } ?? volatilePrompt
      let cacheKey = ContextPromptCacheKey.director
      let started = DispatchTime.now().uptimeNanoseconds
      let result = try await completion(
        ModelQoS.Proactivity.reasoningOperation,
        prompt,
        uncachedPrompt,
        nil,
        ContextProactivityEngine.schema(allowLookup: allowLookup),
        cacheKey,
        800,
        nil)
      let elapsedNanoseconds = DispatchTime.now().uptimeNanoseconds - started
      let latencyMs = min(90_000, Int((Double(elapsedNanoseconds) / 1_000_000).rounded()))
      guard let data = result.content.data(using: .utf8) else {
        throw ContextBucketDirectorProbeError.invalidModelResponse
      }
      let decision: ContextDirectorDecision
      do {
        decision = try JSONDecoder().decode(ContextDirectorDecision.self, from: data).clamped()
      } catch {
        throw ContextBucketDirectorProbeError.invalidModelResponse
      }

      let citedRefs = ContextDirectorRetrievalHop.partitionCitedRefs(decision.bucketEntryRefs)
      let validRetrieved = ContextDirectorRetrievalHop.validatedRetrievedRefs(
        citedRefs.retrieved, allowed: Set(input.retrieved.map(\.ref)))
      // The engine validates citations against the store; the probe has no
      // store, so a citation validates only when it appears verbatim in the
      // supplied snapshot text — the same "cite only supplied refs" rule.
      let suppliedText = ([input.frozen] + input.tail + input.validatedFacts).joined(separator: "\n")
      let validBucketRefs = citedRefs.bucket.filter { suppliedText.contains($0) }
      let validFactIDs = decision.factIDs.filter { suppliedText.contains($0) }
      // The real grounding guard runs on the replayed decision, so a probe run
      // exercises model -> citation validation -> grounding veto exactly as the
      // engine chains them.
      let groundingPermits =
        decision.decision == "silence"
        ? false
        : ContextDirectorGrounding.permitsNonSilence(
          decision: decision.decision, entryRefs: validBucketRefs, factIDs: validFactIDs,
          retrievedRefs: validRetrieved)
      var output = [
        "decision": String(decision.decision.prefix(32)),
        "title": decision.title,
        "message": decision.message,
        "reasoning": decision.reasoning,
        "bucket_entry_ref_count": "\(citedRefs.bucket.count)",
        "fact_ref_count": "\(decision.factIDs.count)",
        "retrieved_ref_count": "\(validRetrieved.count)",
        "lookup_query": decision.lookupQuery ?? "",
        "grounding_permits": groundingPermits ? "true" : "false",
        "model": ContextProactivityTelemetry.boundedProviderModel(result.providerModel),
        "latency_ms": "\(max(0, latencyMs))",
      ]
      // present=1 continues a grounding-permitted decision into the real
      // presentation gate stack, completing the model -> grounding ->
      // presentation chain the engine runs for an organic delivery.
      if input.present {
        guard groundingPermits else {
          output["presentation"] = "not_attempted_grounding_veto_or_silence"
          return output
        }
        let title = decision.title
        let message = decision.message
        let decisionType = decision.decision
        let refDetail = (validBucketRefs + validRetrieved).joined(separator: ", ")
        output["presentation"] = await MainActor.run {
          guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(), !ownerID.isEmpty else {
            return "no_owner"
          }
          let context = FloatingBarNotificationContext(
            sourceTitle: title,
            assistantId: "context-director",
            contextSummary: "probe replay",
            detail: refDetail,
            provenanceRef: "probe-present")
          let presentation = NotificationService.shared.presentContextDirectorNotification(
            ownerID: ownerID,
            title: title,
            message: message,
            decisionType: decisionType,
            context: context)
          return "\(presentation)"
        }
      }
      return output
    }

    private struct Input {
      let bucketID: String
      let version: Int
      let header: String
      let frozen: String
      let tail: [String]
      let validatedFacts: [String]
      let tasks: [ContextDirectorTaskContext]
      let app: String
      let window: String
      let capturedAt: Date
      let notifyWorthiness: Double
      /// Optional. Absent means "unknown", which prints no visit line, so
      /// existing probe callers keep their exact prompt.
      let visitCount: Int
      /// Optional. Lets a probe exercise the recent-delivery prompt section, which is
      /// otherwise only reachable from the live ledger.
      let recentDeliveries: [ContextBucketRecentDelivery]
      /// Optional. Non-empty turns the replay into the visit's *second* director
      /// call, with these items quoted in a RETRIEVED CONTEXT section.
      let retrieved: [ContextRetrievedItem]
      /// Optional. The lookup query echoed into the retrieved section; ignored
      /// when `retrieved` is empty.
      let lookupQuery: String
      /// Optional. "1" continues a grounding-permitted decision into the real
      /// presentation gate stack.
      let present: Bool

      init(params: [String: String]) throws {
        bucketID = try Self.requiredString(params, key: "bucket_id", maxLength: 200)
        let rawVersion = try Self.requiredString(params, key: "version", maxLength: 12)
        guard let parsedVersion = Int(rawVersion), (1...1_000_000).contains(parsedVersion) else {
          throw ContextBucketDirectorProbeError.invalidParams("version")
        }
        version = parsedVersion
        header = try Self.requiredString(params, key: "header", maxLength: 2_400)
        frozen = try Self.frozenString(params["frozen"])
        tail = try Self.requiredStringList(params, key: "tail", maxCount: 20, maxLength: 2_400)
        validatedFacts = try Self.requiredStringList(
          params, key: "validated_facts", maxCount: 20, maxLength: 2_400)
        tasks = try Self.requiredTaskList(params, key: "tasks", maxCount: 20)
        app = try Self.requiredString(params, key: "app", maxLength: 200)
        window = try Self.requiredString(params, key: "window", maxLength: 400)
        let rawCapturedAt = try Self.requiredString(params, key: "captured_at", maxLength: 40)
        guard let parsedCapturedAt = Self.parseTimestamp(rawCapturedAt) else {
          throw ContextBucketDirectorProbeError.invalidParams("captured_at")
        }
        capturedAt = parsedCapturedAt
        let rawWorthiness = try Self.requiredString(params, key: "notify_worthiness", maxLength: 16)
        guard let parsedWorthiness = Double(rawWorthiness), (0...1).contains(parsedWorthiness) else {
          throw ContextBucketDirectorProbeError.invalidParams("notify_worthiness")
        }
        notifyWorthiness = parsedWorthiness
        if let rawVisitCount = params["visit_count"], !rawVisitCount.isEmpty {
          guard let parsedVisitCount = Int(rawVisitCount), (0...1_000_000).contains(parsedVisitCount)
          else {
            throw ContextBucketDirectorProbeError.invalidParams("visit_count")
          }
          visitCount = parsedVisitCount
        } else {
          visitCount = 0
        }
        recentDeliveries = try Self.optionalRecentDeliveryList(
          params, key: "recent_deliveries",
          maxCount: ContextBucketRecentDelivery.promptCap)
        retrieved = try Self.optionalRetrievedList(
          params, key: "retrieved",
          maxCount: ContextDirectorRetrievalHop.maximumPromptItems)
        lookupQuery = params["lookup_query"].map { String($0.prefix(200)) } ?? ""
        present = params["present"] == "1"
      }

      /// Absent means "first-call replay", so existing probe callers keep their
      /// exact prompt, schema, and behaviour.
      private static func optionalRetrievedList(
        _ params: [String: String],
        key: String,
        maxCount: Int
      ) throws -> [ContextRetrievedItem] {
        guard let raw = params[key], !raw.isEmpty else { return [] }
        guard let data = raw.data(using: .utf8),
          let values = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
          values.count <= maxCount
        else {
          throw ContextBucketDirectorProbeError.invalidParams(key)
        }
        return try values.map { value in
          guard let ref = value["ref"] as? String, !ref.isEmpty, ref.count <= 200,
            let preview = value["preview"] as? String, !preview.isEmpty, preview.count <= 2_400
          else {
            throw ContextBucketDirectorProbeError.invalidParams(key)
          }
          let title = (value["title"] as? String) ?? ""
          let createdAt = value["created_at"] as? String
          guard title.count <= 400, (createdAt?.count ?? 0) <= 40 else {
            throw ContextBucketDirectorProbeError.invalidParams(key)
          }
          return ContextRetrievedItem(ref: ref, title: title, preview: preview, createdAt: createdAt)
        }
      }

      /// Absent means "no recent deliveries", so existing probe callers keep their behaviour.
      private static func optionalRecentDeliveryList(
        _ params: [String: String],
        key: String,
        maxCount: Int
      ) throws -> [ContextBucketRecentDelivery] {
        guard let raw = params[key], !raw.isEmpty else { return [] }
        guard let data = raw.data(using: .utf8),
          let values = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
          values.count <= maxCount
        else {
          throw ContextBucketDirectorProbeError.invalidParams(key)
        }
        return try values.map { value in
          guard let decisionType = value["decision_type"] as? String,
            !decisionType.isEmpty, decisionType.count <= 32,
            let rawDeliveredAt = value["delivered_at"] as? String,
            let deliveredAt = Self.parseTimestamp(rawDeliveredAt)
          else {
            throw ContextBucketDirectorProbeError.invalidParams(key)
          }
          let message = value["message"] as? String
          guard (message?.count ?? 0) <= 2_400 else {
            throw ContextBucketDirectorProbeError.invalidParams(key)
          }
          return ContextBucketRecentDelivery(
            decisionType: decisionType, message: message, deliveredAt: deliveredAt)
        }
      }

      private static func requiredString(
        _ params: [String: String],
        key: String,
        maxLength: Int
      ) throws -> String {
        guard let raw = params[key], !raw.isEmpty, raw.count <= maxLength else {
          throw ContextBucketDirectorProbeError.invalidParams(key)
        }
        return raw
      }

      private static func requiredStringList(
        _ params: [String: String],
        key: String,
        maxCount: Int,
        maxLength: Int
      ) throws -> [String] {
        guard let raw = params[key], let data = raw.data(using: .utf8),
          let values = try? JSONSerialization.jsonObject(with: data) as? [Any],
          values.count <= maxCount,
          values.allSatisfy({ $0 is String })
        else {
          throw ContextBucketDirectorProbeError.invalidParams(key)
        }
        let strings = values.compactMap { $0 as? String }
        guard strings.allSatisfy({ $0.count <= maxLength }) else {
          throw ContextBucketDirectorProbeError.invalidParams(key)
        }
        return strings
      }

      private static func requiredTaskList(
        _ params: [String: String],
        key: String,
        maxCount: Int
      ) throws -> [ContextDirectorTaskContext] {
        guard let raw = params[key], let data = raw.data(using: .utf8),
          let values = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
          values.count <= maxCount
        else {
          throw ContextBucketDirectorProbeError.invalidParams(key)
        }
        return try values.enumerated().map { index, value in
          guard let description = value["description"] as? String,
            !description.isEmpty,
            description.count <= ContextDirectorTaskContext.maximumDescriptionLength
          else {
            throw ContextBucketDirectorProbeError.invalidParams(key)
          }
          let dueAt: Date?
          if value["due_at"] == nil || value["due_at"] is NSNull {
            dueAt = nil
          } else if let rawDueAt = value["due_at"] as? String,
            let parsedDueAt = parseTimestamp(rawDueAt)
          {
            dueAt = parsedDueAt
          } else {
            throw ContextBucketDirectorProbeError.invalidParams(key)
          }
          // DEBUG probe: accept a caller-supplied id so a probe can assert on
          // exact task handles, and fall back to a stable synthetic one so the
          // prompt's handles stay well-formed when the caller omits it.
          let id = (value["id"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "probe-\(index)"
          return ContextDirectorTaskContext(id: id, description: description, dueAt: dueAt)
        }
      }

      private static func parseTimestamp(_ value: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
      }

      private static func frozenString(_ raw: String?) throws -> String {
        guard let raw, !raw.isEmpty else {
          throw ContextBucketDirectorProbeError.invalidParams("frozen")
        }
        if let data = raw.data(using: .utf8),
          let values = try? JSONSerialization.jsonObject(with: data) as? [Any]
        {
          guard values.count <= 20, values.allSatisfy({ $0 is String }) else {
            throw ContextBucketDirectorProbeError.invalidParams("frozen")
          }
          let strings = values.compactMap { $0 as? String }
          guard strings.allSatisfy({ $0.count <= 2_400 }) else {
            throw ContextBucketDirectorProbeError.invalidParams("frozen")
          }
          return strings.joined(separator: "\n")
        }
        guard raw.count <= 12_000 else {
          throw ContextBucketDirectorProbeError.invalidParams("frozen")
        }
        return raw
      }
    }
  }

  enum ContextBucketDirectorProbeError: LocalizedError {
    case invalidParams(String)
    case invalidModelResponse
    case nonProductionOnly

    var errorDescription: String? {
      switch self {
      case .invalidParams(let key): return "invalid synthetic parameter: \(key)"
      case .invalidModelResponse: return "invalid director model response"
      case .nonProductionOnly: return "context director probe is disabled on production bundles"
      }
    }
  }
#endif
