#if DEBUG
  import Foundation

  /// Non-production-only replay of the context director's model boundary.
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
        operation, prompt, imageData, jsonSchema, cacheKey, maxCompletionTokens,
        authorizationSnapshot in
        let schema = SendableSchema(jsonSchema)
        return try await client.complete(
          operation: operation,
          prompt: prompt,
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
    /// ABI; list-valued fields must be JSON arrays of strings.
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
        notifyWorthiness: 1)
      let frame = CapturedFrame(
        jpegData: Data(),
        appName: input.app,
        windowTitle: input.window,
        frameNumber: 0)
      let prompt = ContextProactivityPromptBuilder.directorPrompt(
        snapshot: snapshot,
        tasks: input.tasks,
        frame: frame)
      let cacheKey = "bucket:\(snapshot.bucketID):v\(snapshot.version)"
      let started = DispatchTime.now().uptimeNanoseconds
      let result = try await completion(
        ModelQoS.Proactivity.reasoningOperation,
        prompt,
        nil,
        ContextProactivityEngine.schema,
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

      return [
        "decision": String(decision.decision.prefix(32)),
        "title": String(decision.title.prefix(120)),
        "message": String(decision.message.prefix(600)),
        "reasoning": String(decision.reasoning.prefix(1_200)),
        "bucket_entry_ref_count": "\(decision.bucketEntryRefs.count)",
        "fact_ref_count": "\(decision.factIDs.count)",
        "model": ContextProactivityTelemetry.boundedProviderModel(result.providerModel),
        "latency_ms": "\(max(0, latencyMs))",
      ]
    }

    private struct Input {
      let bucketID: String
      let version: Int
      let header: String
      let frozen: String
      let tail: [String]
      let validatedFacts: [String]
      let tasks: [String]
      let app: String
      let window: String

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
        tasks = try Self.requiredStringList(params, key: "tasks", maxCount: 20, maxLength: 600)
        app = try Self.requiredString(params, key: "app", maxLength: 200)
        window = try Self.requiredString(params, key: "window", maxLength: 400)
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
