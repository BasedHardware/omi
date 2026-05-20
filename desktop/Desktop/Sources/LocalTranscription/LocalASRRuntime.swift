import Foundation

enum LocalTranscriptionModel: String, CaseIterable, Codable, Equatable, Hashable {
  case tiny
  case base
  case small
  case medium
  case largeV3Turbo = "large_v3_turbo"
}

struct LocalTranscriptionPlan: Equatable {
  var engine: LocalTranscriptionEngine
  var model: LocalTranscriptionModel
  var quality: TranscriptionQualityPreset
}

struct LocalASRTranscriptionRequest: Codable, Equatable {
  var requestId: String
  var audioPath: String
  var language: String
  var sampleRate: Int
  var channels: Int
  var engine: LocalTranscriptionEngine
  var model: LocalTranscriptionModel
  var fixtureSegments: [LocalASRTranscriptSegment]?

  enum CodingKeys: String, CodingKey {
    case requestId = "request_id"
    case audioPath = "audio_path"
    case language
    case sampleRate = "sample_rate"
    case channels
    case engine
    case model
    case fixtureSegments = "fixture_segments"
  }
}

struct LocalASRTranscriptionResponse: Codable, Equatable {
  var requestId: String
  var engine: LocalTranscriptionEngine
  var model: LocalTranscriptionModel
  var language: String
  var segments: [LocalASRTranscriptSegment]
  var fixture: Bool

  enum CodingKeys: String, CodingKey {
    case requestId = "request_id"
    case engine
    case model
    case language
    case segments
    case fixture
  }
}

struct LocalASRCapabilityResponse: Codable, Equatable {
  var engines: [LocalASREngineCapability]
}

struct LocalASREngineCapability: Codable, Equatable {
  var engine: LocalTranscriptionEngine
  var available: Bool
  var reason: String?
}

struct LocalASRTranscriptSegment: Codable, Equatable {
  var id: String?
  var speaker: Int?
  var text: String
  var start: Double
  var end: Double

  func normalized(defaultSpeaker: Int = 0) -> NormalizedTranscriptSegment {
    NormalizedTranscriptSegment(
      segmentId: id,
      speaker: speaker ?? defaultSpeaker,
      speakerLabel: nil,
      text: text,
      start: start,
      end: end,
      isUser: true,
      personId: nil,
      translations: []
    )
  }
}

struct LocalASRHelperClient {
  var executableURL: URL
  var timeoutSeconds: TimeInterval = 60

  func transcribe(_ request: LocalASRTranscriptionRequest) async throws
    -> LocalASRTranscriptionResponse
  {
    let process = Process()
    process.executableURL = executableURL

    let input = Pipe()
    let output = Pipe()
    let errors = Pipe()
    process.standardInput = input
    process.standardOutput = output
    process.standardError = errors

    try process.run()
    let requestData = try JSONEncoder.localASR.encode(request)
    input.fileHandleForWriting.write(requestData)
    try? input.fileHandleForWriting.close()

    return try await withTimeout(seconds: timeoutSeconds) {
      process.waitUntilExit()
      let outputData = output.fileHandleForReading.readDataToEndOfFile()
      if process.terminationStatus != 0 {
        let errorText =
          String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        throw TranscriptionService.TranscriptionError.webSocketError(
          "Local ASR helper exited with status \(process.terminationStatus): \(errorText)"
        )
      }
      return try JSONDecoder.localASR.decode(LocalASRTranscriptionResponse.self, from: outputData)
    }
  }

  private func withTimeout<T: Sendable>(
    seconds: TimeInterval,
    operation: @escaping @Sendable () throws -> T
  ) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
      group.addTask {
        try operation()
      }
      group.addTask {
        try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        throw CancellationError()
      }
      guard let result = try await group.next() else {
        throw CancellationError()
      }
      group.cancelAll()
      return result
    }
  }
}

enum LocalASRHelperLocator {
  static let environmentKey = "OMI_LOCAL_ASR_HELPER_PATH"

  static func defaultExecutableURL(
    environment: [String: String] = ProcessInfo.processInfo.environment,
    bundle: Bundle = .main,
    fileManager: FileManager = .default
  ) -> URL? {
    if let override = environment[environmentKey], !override.isEmpty {
      let url = URL(fileURLWithPath: override)
      return fileManager.isExecutableFile(atPath: url.path) ? url : nil
    }

    let bundleCandidates = [
      bundle.url(forResource: "local-asr-helper", withExtension: nil),
      bundle.resourceURL?.appendingPathComponent("local-asr-helper"),
    ].compactMap { $0 }

    if let bundled = bundleCandidates.first(where: {
      fileManager.isExecutableFile(atPath: $0.path)
    }) {
      return bundled
    }

    #if DEBUG
      let currentDirectory = URL(fileURLWithPath: fileManager.currentDirectoryPath)
      let debugCandidates = [
        currentDirectory.appendingPathComponent("local-asr-helper/target/debug/local-asr-helper"),
        currentDirectory.appendingPathComponent(
          "../local-asr-helper/target/debug/local-asr-helper"),
        currentDirectory.appendingPathComponent(
          "../../local-asr-helper/target/debug/local-asr-helper"),
        currentDirectory.appendingPathComponent(
          "desktop/local-asr-helper/target/debug/local-asr-helper"),
      ]
      return debugCandidates.first { fileManager.isExecutableFile(atPath: $0.path) }
    #else
      return nil
    #endif
  }

  static func detectedEngines(executableURL: URL? = defaultExecutableURL())
    -> Set<LocalTranscriptionEngine>
  {
    guard let executableURL else { return [] }
    let process = Process()
    process.executableURL = executableURL
    process.arguments = ["--capabilities"]

    let output = Pipe()
    process.standardOutput = output
    process.standardError = Pipe()

    do {
      try process.run()
    } catch {
      return []
    }

    let deadline = Date().addingTimeInterval(8)
    while process.isRunning && Date() < deadline {
      Thread.sleep(forTimeInterval: 0.05)
    }
    if process.isRunning {
      process.terminate()
      return []
    }
    guard process.terminationStatus == 0 else { return [] }

    let outputData = output.fileHandleForReading.readDataToEndOfFile()
    guard
      let response = try? JSONDecoder.localASR.decode(
        LocalASRCapabilityResponse.self, from: outputData)
    else {
      return []
    }

    return Set(response.engines.filter(\.available).map(\.engine))
  }
}

struct LocalASRBatchTranscriber {
  typealias RequestHandler = (LocalASRTranscriptionRequest) async throws
    -> LocalASRTranscriptionResponse

  var requestHandler: RequestHandler
  var temporaryDirectory: URL
  var fileManager: FileManager
  var makeRequestId: () -> String

  init(
    executableURL: URL,
    timeoutSeconds: TimeInterval = 60,
    temporaryDirectory: URL = FileManager.default.temporaryDirectory,
    fileManager: FileManager = .default,
    makeRequestId: @escaping () -> String = { UUID().uuidString }
  ) {
    let client = LocalASRHelperClient(executableURL: executableURL, timeoutSeconds: timeoutSeconds)
    self.init(
      requestHandler: { request in
        try await client.transcribe(request)
      },
      temporaryDirectory: temporaryDirectory,
      fileManager: fileManager,
      makeRequestId: makeRequestId
    )
  }

  init(
    requestHandler: @escaping RequestHandler,
    temporaryDirectory: URL = FileManager.default.temporaryDirectory,
    fileManager: FileManager = .default,
    makeRequestId: @escaping () -> String = { UUID().uuidString }
  ) {
    self.requestHandler = requestHandler
    self.temporaryDirectory = temporaryDirectory
    self.fileManager = fileManager
    self.makeRequestId = makeRequestId
  }

  func transcribe(
    audioData: Data,
    language: String,
    plan: LocalTranscriptionPlan
  ) async throws -> [NormalizedTranscriptSegment] {
    let requestId = makeRequestId()
    let audioURL = temporaryDirectory.appendingPathComponent("\(requestId).pcm")
    try audioData.write(to: audioURL, options: .atomic)
    defer { try? fileManager.removeItem(at: audioURL) }

    let response = try await requestHandler(
      LocalASRTranscriptionRequest(
        requestId: requestId,
        audioPath: audioURL.path,
        language: language,
        sampleRate: 16000,
        channels: 1,
        engine: plan.engine,
        model: plan.model,
        fixtureSegments: nil
      )
    )

    var merger = LocalTranscriptMerger()
    return merger.merge(response.segments.map { $0.normalized() })
  }
}

struct PTTBatchTranscriptionResult: Equatable {
  var provider: TranscriptionProviderKind
  var transcript: String?
  var fallbackReason: String?
}

struct PTTBatchTranscriptionRouter {
  typealias CloudTranscriber = (Data, String, [String]) async throws -> String?
  typealias LocalTranscriber = (Data, String, LocalTranscriptionPlan) async throws
    -> [NormalizedTranscriptSegment]

  var selection: () -> TranscriptionProviderSelection
  var capabilities: () -> LocalTranscriptionCapabilities
  var cloudTranscribe: CloudTranscriber
  var localTranscribe: LocalTranscriber
  var policy: TranscriptionProviderPolicy

  init(
    selection: @escaping () -> TranscriptionProviderSelection = { .default },
    capabilities: @escaping () -> LocalTranscriptionCapabilities = {
      LocalTranscriptionCapabilityDetector(
        availableEngines: { LocalASRHelperLocator.detectedEngines() }
      ).detect()
    },
    cloudTranscribe: @escaping CloudTranscriber = { audioData, language, keywords in
      try await TranscriptionService.batchTranscribe(
        audioData: audioData,
        language: language,
        contextKeywords: keywords
      )
    },
    localTranscribe: @escaping LocalTranscriber = { audioData, language, plan in
      guard let executableURL = LocalASRHelperLocator.defaultExecutableURL() else {
        throw TranscriptionService.TranscriptionError.webSocketError(
          "Local ASR helper is not available"
        )
      }
      return try await LocalASRBatchTranscriber(executableURL: executableURL).transcribe(
        audioData: audioData,
        language: language,
        plan: plan
      )
    },
    policy: TranscriptionProviderPolicy = TranscriptionProviderPolicy()
  ) {
    self.selection = selection
    self.capabilities = capabilities
    self.cloudTranscribe = cloudTranscribe
    self.localTranscribe = localTranscribe
    self.policy = policy
  }

  func transcribe(audioData: Data, language: String, contextKeywords: [String]) async throws
    -> PTTBatchTranscriptionResult
  {
    let currentSelection = selection()
    let resolved = policy.resolve(selection: currentSelection, capabilities: capabilities())

    if resolved.provider == .local, let plan = resolved.localPlan {
      let segments = try await localTranscribe(audioData, language, plan)
      let transcript = segments.map(\.text).joined(separator: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      return PTTBatchTranscriptionResult(
        provider: .local,
        transcript: transcript.isEmpty ? nil : transcript,
        fallbackReason: resolved.fallbackReason
      )
    }

    if currentSelection.mode == .local {
      throw TranscriptionService.TranscriptionError.webSocketError(
        resolved.fallbackReason ?? "No local transcription engine is available"
      )
    }

    let transcript = try await cloudTranscribe(audioData, language, contextKeywords)
    return PTTBatchTranscriptionResult(
      provider: .cloud,
      transcript: transcript,
      fallbackReason: resolved.fallbackReason
    )
  }
}

struct BackgroundTranscriptionRoutingDecision: Equatable {
  var useCloudBackend: Bool
  var unsupportedLocalReason: String?
}

struct BackgroundTranscriptionRoutingGuard {
  var policy: TranscriptionProviderPolicy = TranscriptionProviderPolicy()

  func decide(
    selection: TranscriptionProviderSelection,
    capabilities: LocalTranscriptionCapabilities
  ) -> BackgroundTranscriptionRoutingDecision {
    let resolved = policy.resolve(selection: selection, capabilities: capabilities)
    if selection.mode == .local, resolved.provider != .local {
      return BackgroundTranscriptionRoutingDecision(
        useCloudBackend: false,
        unsupportedLocalReason: resolved.fallbackReason
          ?? "No local transcription engine is available"
      )
    }

    guard resolved.provider == .local else {
      return BackgroundTranscriptionRoutingDecision(
        useCloudBackend: true,
        unsupportedLocalReason: resolved.fallbackReason
      )
    }

    return BackgroundTranscriptionRoutingDecision(
      useCloudBackend: false,
      unsupportedLocalReason:
        "Local background transcription is not available until local finalization can persist conversations without backend force-processing."
    )
  }
}

struct LocalTranscriptMerger {
  private(set) var segments: [NormalizedTranscriptSegment] = []
  private let duplicateOverlapThreshold: Double

  init(duplicateOverlapThreshold: Double = 0.8) {
    self.duplicateOverlapThreshold = duplicateOverlapThreshold
  }

  mutating func merge(_ incomingSegments: [NormalizedTranscriptSegment])
    -> [NormalizedTranscriptSegment]
  {
    for incoming in incomingSegments
    where !incoming.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      upsert(incoming)
    }
    segments.sort { lhs, rhs in
      if lhs.start == rhs.start {
        return lhs.end < rhs.end
      }
      return lhs.start < rhs.start
    }
    return segments
  }

  private mutating func upsert(_ incoming: NormalizedTranscriptSegment) {
    if let segmentId = incoming.segmentId,
      let index = segments.firstIndex(where: { $0.segmentId == segmentId })
    {
      segments[index] = preferredSegment(existing: segments[index], incoming: incoming)
      return
    }

    if let index = segments.firstIndex(where: { isDuplicate($0, incoming) }) {
      segments[index] = preferredSegment(existing: segments[index], incoming: incoming)
      return
    }

    if let index = segments.firstIndex(where: { canMergeOverlap($0, incoming) }) {
      segments[index] = mergedOverlap(segments[index], incoming)
      return
    }

    segments.append(incoming)
  }

  private func isDuplicate(
    _ existing: NormalizedTranscriptSegment, _ incoming: NormalizedTranscriptSegment
  ) -> Bool {
    guard normalizedText(existing.text) == normalizedText(incoming.text) else { return false }
    let intersection = max(0, min(existing.end, incoming.end) - max(existing.start, incoming.start))
    let shorterDuration = max(
      0.001, min(existing.end - existing.start, incoming.end - incoming.start))
    return intersection / shorterDuration >= duplicateOverlapThreshold
  }

  private func canMergeOverlap(
    _ existing: NormalizedTranscriptSegment,
    _ incoming: NormalizedTranscriptSegment
  ) -> Bool {
    guard existing.speaker == incoming.speaker else { return false }
    guard min(existing.end, incoming.end) > max(existing.start, incoming.start) else {
      return false
    }
    return edgeTokenOverlap(existing.text, incoming.text) > 0
  }

  private func mergedOverlap(
    _ existing: NormalizedTranscriptSegment,
    _ incoming: NormalizedTranscriptSegment
  ) -> NormalizedTranscriptSegment {
    let existingFirst = existing.start <= incoming.start
    let first = existingFirst ? existing : incoming
    let second = existingFirst ? incoming : existing
    let overlap = edgeTokenOverlap(first.text, second.text)
    let suffix = tokenized(second.text).dropFirst(overlap).joined(separator: " ")

    var merged = first
    merged.segmentId = first.segmentId ?? second.segmentId
    merged.start = min(first.start, second.start)
    merged.end = max(first.end, second.end)
    merged.text = suffix.isEmpty ? first.text : "\(first.text) \(suffix)"
    return merged
  }

  private func edgeTokenOverlap(_ first: String, _ second: String) -> Int {
    let left = tokenized(first)
    let right = tokenized(second)
    guard !left.isEmpty, !right.isEmpty else { return 0 }

    let maxOverlap = min(left.count, right.count)
    for count in stride(from: maxOverlap, through: 1, by: -1) {
      if Array(left.suffix(count)) == Array(right.prefix(count)) {
        return count
      }
    }
    return 0
  }

  private func preferredSegment(
    existing: NormalizedTranscriptSegment,
    incoming: NormalizedTranscriptSegment
  ) -> NormalizedTranscriptSegment {
    if normalizedText(existing.text) == normalizedText(incoming.text),
      existing.text.count <= incoming.text.count
    {
      return existing
    }
    if incoming.end - incoming.start > existing.end - existing.start {
      return incoming
    }
    if incoming.text.count > existing.text.count {
      return incoming
    }
    return existing
  }

  private func normalizedText(_ value: String) -> String {
    value.lowercased()
      .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func tokenized(_ value: String) -> [String] {
    normalizedText(value).split(separator: " ").map(String.init)
  }
}

extension JSONEncoder {
  fileprivate static var localASR: JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return encoder
  }
}

extension JSONDecoder {
  fileprivate static var localASR: JSONDecoder {
    JSONDecoder()
  }
}
