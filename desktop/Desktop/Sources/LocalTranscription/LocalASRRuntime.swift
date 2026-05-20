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
    LocalASRAddonManager.activateIfInstalled()
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

    let didExit = await waitForExit(process, timeoutSeconds: timeoutSeconds)
    guard didExit else {
      if process.isRunning {
        process.terminate()
        _ = await waitForExit(process, timeoutSeconds: 2)
      }
      throw TranscriptionService.TranscriptionError.webSocketError(
        "Local ASR helper timed out after \(Int(timeoutSeconds))s"
      )
    }

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

  private func waitForExit(_ process: Process, timeoutSeconds: TimeInterval) async -> Bool {
    let deadline = Date().addingTimeInterval(timeoutSeconds)
    while process.isRunning && Date() < deadline {
      try? await Task.sleep(nanoseconds: 100_000_000)
    }
    return !process.isRunning
  }
}

enum LocalASRHelperLocator {
  static let environmentKey = "OMI_LOCAL_ASR_HELPER_PATH"
  private static let cacheLock = NSLock()
  private static var cachedEngines: Set<LocalTranscriptionEngine>?
  private static var cachedExecutablePath: String?
  private static var cachedAt: Date?
  private static var refreshInFlight = false
  private static var refreshInFlightExecutablePath: String?

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
    LocalASRAddonManager.activateIfInstalled()
    let executablePath = executableURL?.standardizedFileURL.path
    if Thread.isMainThread {
      if let cached = cachedEnginesIfFresh(for: executablePath) {
        return cached
      }
      if executablePath != defaultExecutableURL()?.standardizedFileURL.path {
        let engines = detectedEnginesBlocking(executableURL: executableURL)
        storeCachedEngines(engines, for: executablePath)
        return engines
      }
      refreshDetectedEnginesInBackground(executableURL: executableURL)
      return cachedEnginesValue(for: executablePath) ?? []
    }
    let engines = detectedEnginesBlocking(executableURL: executableURL)
    storeCachedEngines(engines, for: executablePath)
    return engines
  }

  static func refreshDetectedEngines(executableURL: URL? = defaultExecutableURL()) async
    -> Set<LocalTranscriptionEngine>
  {
    LocalASRAddonManager.activateIfInstalled()
    return await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .userInitiated).async {
        let engines = detectedEnginesBlocking(executableURL: executableURL)
        storeCachedEngines(engines, for: executableURL?.standardizedFileURL.path)
        continuation.resume(returning: engines)
      }
    }
  }

  private static func detectedEnginesBlocking(executableURL: URL?)
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

    if process.isRunning {
      let finished = DispatchSemaphore(value: 0)
      process.terminationHandler = { _ in finished.signal() }
      if finished.wait(timeout: .now() + 8) == .timedOut {
        process.terminate()
        return []
      }
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

  private static func cachedEnginesIfFresh(
    for executablePath: String?,
    maxAge: TimeInterval = 60
  ) -> Set<LocalTranscriptionEngine>? {
    cacheLock.lock()
    defer { cacheLock.unlock() }
    guard cachedExecutablePath == executablePath, let cachedEngines, let cachedAt,
      Date().timeIntervalSince(cachedAt) <= maxAge
    else {
      return nil
    }
    return cachedEngines
  }

  private static func cachedEnginesValue(for executablePath: String?) -> Set<
    LocalTranscriptionEngine
  >? {
    cacheLock.lock()
    defer { cacheLock.unlock() }
    guard cachedExecutablePath == executablePath else { return nil }
    return cachedEngines
  }

  private static func storeCachedEngines(
    _ engines: Set<LocalTranscriptionEngine>, for executablePath: String?
  ) {
    cacheLock.lock()
    cachedEngines = engines
    cachedExecutablePath = executablePath
    cachedAt = Date()
    refreshInFlight = false
    refreshInFlightExecutablePath = nil
    cacheLock.unlock()
  }

  private static func refreshDetectedEnginesInBackground(executableURL: URL?) {
    let executablePath = executableURL?.standardizedFileURL.path
    cacheLock.lock()
    if refreshInFlight, refreshInFlightExecutablePath == executablePath {
      cacheLock.unlock()
      return
    }
    refreshInFlight = true
    refreshInFlightExecutablePath = executablePath
    cacheLock.unlock()

    DispatchQueue.global(qos: .utility).async {
      let engines = detectedEnginesBlocking(executableURL: executableURL)
      storeCachedEngines(engines, for: executablePath)
    }
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

struct LocalBackgroundChunkerConfiguration: Equatable {
  var sampleRate: Int = 16000
  var bytesPerSample: Int = 2
  var maxChunkDuration: TimeInterval = 15
  var minChunkDuration: TimeInterval = 1
  var overlapDuration: TimeInterval = 1
  var silenceWindowDuration: TimeInterval = 0.35
  var silenceAmplitudeThreshold: Int16 = 256
  var speechPeakAmplitudeThreshold: Int16 = 512
  var speechRMSAmplitudeThreshold: Double = 64
  var maxPendingChunks: Int = 4

  var maxChunkSamples: Int { max(1, Int(maxChunkDuration * Double(sampleRate))) }
  var minChunkSamples: Int { max(1, Int(minChunkDuration * Double(sampleRate))) }
  var overlapSamples: Int {
    min(max(0, Int(overlapDuration * Double(sampleRate))), max(0, maxChunkSamples - 1))
  }
  var silenceWindowSamples: Int { max(1, Int(silenceWindowDuration * Double(sampleRate))) }
}

struct LocalBackgroundAudioChunk: Equatable {
  var sequence: Int
  var audioData: Data
  var startTime: Double
  var endTime: Double
  var sampleRate: Int
  var overlappedStartTime: Double?

  var duration: Double {
    endTime - startTime
  }
}

struct LocalBackgroundIngestResult: Equatable {
  var enqueuedChunks: [LocalBackgroundAudioChunk]
  var droppedChunks: [LocalBackgroundAudioChunk]
  var pendingChunkCount: Int
}

struct LocalBackgroundASRRawChunkResult: Equatable {
  var chunk: LocalBackgroundAudioChunk
  var response: LocalASRTranscriptionResponse
  var remappedSegments: [NormalizedTranscriptSegment]
  var latencySeconds: TimeInterval

  var joinedText: String {
    remappedSegments.map(\.text).joined(separator: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

struct LocalBackgroundTranscriptSnapshot: Equatable {
  var rawChunkResults: [LocalBackgroundASRRawChunkResult]
  var mergedSegments: [NormalizedTranscriptSegment]

  var joinedTranscript: String {
    mergedSegments.map(\.text).joined(separator: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

enum LocalBackgroundSessionState: String, Equatable {
  case recording
  case transcribingBacklog = "transcribing_backlog"
  case finalizing
  case finalized
  case failed
}

struct BackgroundConversationFinalizationPolicy {
  enum Owner: Equatable {
    case cloudBackend
    case localBackground
  }

  func shouldForceProcessBackend(owner: Owner) -> Bool {
    owner == .cloudBackend
  }
}

struct LocalBackgroundAudioChunker {
  private var configuration: LocalBackgroundChunkerConfiguration
  private var buffer = Data()
  private var bufferStartTime: Double?
  private var nextSequence = 0

  init(configuration: LocalBackgroundChunkerConfiguration = LocalBackgroundChunkerConfiguration()) {
    self.configuration = configuration
  }

  mutating func append(pcmData: Data, startTime: Double) -> [LocalBackgroundAudioChunk] {
    guard !pcmData.isEmpty else { return [] }
    if buffer.isEmpty {
      bufferStartTime = startTime
    }
    buffer.append(alignedPCM(pcmData))
    return emitBoundedChunks(flush: false)
  }

  mutating func flush() -> [LocalBackgroundAudioChunk] {
    emitBoundedChunks(flush: true)
  }

  private mutating func emitBoundedChunks(flush: Bool) -> [LocalBackgroundAudioChunk] {
    var chunks: [LocalBackgroundAudioChunk] = []
    while sampleCount(in: buffer) >= configuration.maxChunkSamples
      || (flush && sampleCount(in: buffer) > 0)
    {
      let availableSamples = sampleCount(in: buffer)
      let cutSamples: Int
      if flush {
        cutSamples = availableSamples
      } else {
        cutSamples = cutSample(availableSamples: availableSamples)
      }

      guard cutSamples > 0, let startTime = bufferStartTime else { break }
      let byteCount = cutSamples * configuration.bytesPerSample
      let audioData = buffer.prefix(byteCount)
      let endTime = startTime + Double(cutSamples) / Double(configuration.sampleRate)
      let overlappedStartTime = nextSequence == 0 ? nil : startTime
      chunks.append(
        LocalBackgroundAudioChunk(
          sequence: nextSequence,
          audioData: Data(audioData),
          startTime: startTime,
          endTime: endTime,
          sampleRate: configuration.sampleRate,
          overlappedStartTime: overlappedStartTime
        )
      )
      nextSequence += 1

      if flush {
        buffer.removeFirst(byteCount)
        bufferStartTime = buffer.isEmpty ? nil : endTime
      } else {
        let retainFromSample = max(0, cutSamples - configuration.overlapSamples)
        let retainFromByte = retainFromSample * configuration.bytesPerSample
        buffer.removeFirst(retainFromByte)
        bufferStartTime = startTime + Double(retainFromSample) / Double(configuration.sampleRate)
      }
    }
    return chunks
  }

  private func cutSample(availableSamples: Int) -> Int {
    let boundedSamples = min(availableSamples, configuration.maxChunkSamples)
    if let silenceBoundary = lastSilenceBoundary(before: boundedSamples) {
      return silenceBoundary
    }
    return boundedSamples
  }

  private func lastSilenceBoundary(before upperBound: Int) -> Int? {
    let window = configuration.silenceWindowSamples
    let minimum = configuration.minChunkSamples
    guard upperBound >= minimum + window else { return nil }

    let samples = int16Samples(from: buffer)
    guard samples.count >= upperBound else { return nil }

    var index = upperBound - window
    while index >= minimum {
      let range = index..<(index + window)
      if range.allSatisfy({
        abs(Int32(samples[$0])) <= Int32(configuration.silenceAmplitudeThreshold)
      }) {
        return index + window
      }
      index -= window
    }
    return nil
  }

  private func alignedPCM(_ data: Data) -> Data {
    if data.count % configuration.bytesPerSample == 0 {
      return data
    }
    return data.dropLast(data.count % configuration.bytesPerSample)
  }

  private func sampleCount(in data: Data) -> Int {
    data.count / configuration.bytesPerSample
  }

  private func int16Samples(from data: Data) -> [Int16] {
    data.withUnsafeBytes { rawBuffer in
      Array(rawBuffer.bindMemory(to: Int16.self))
    }
  }
}

final class LocalBackgroundTranscriptionSession {
  typealias RequestHandler = (LocalASRTranscriptionRequest) async throws
    -> LocalASRTranscriptionResponse

  private let language: String
  private let plan: LocalTranscriptionPlan
  private let configuration: LocalBackgroundChunkerConfiguration
  private let requestHandler: RequestHandler
  private let temporaryDirectory: URL
  private let fileManager: FileManager
  private let makeRequestId: () -> String
  private let now: () -> Date
  private var chunker: LocalBackgroundAudioChunker
  private var pendingChunks: [LocalBackgroundAudioChunk] = []
  private var merger = LocalTranscriptMerger()
  private(set) var rawChunkResults: [LocalBackgroundASRRawChunkResult] = []
  private(set) var droppedChunkCount = 0
  var pendingChunkCount: Int { pendingChunks.count }

  init(
    language: String,
    plan: LocalTranscriptionPlan,
    configuration: LocalBackgroundChunkerConfiguration = LocalBackgroundChunkerConfiguration(),
    executableURL: URL,
    timeoutSeconds: TimeInterval = 60,
    temporaryDirectory: URL = FileManager.default.temporaryDirectory,
    fileManager: FileManager = .default,
    makeRequestId: @escaping () -> String = { UUID().uuidString },
    now: @escaping () -> Date = Date.init
  ) {
    let client = LocalASRHelperClient(executableURL: executableURL, timeoutSeconds: timeoutSeconds)
    self.language = language
    self.plan = plan
    self.configuration = configuration
    self.requestHandler = { request in
      try await client.transcribe(request)
    }
    self.temporaryDirectory = temporaryDirectory
    self.fileManager = fileManager
    self.makeRequestId = makeRequestId
    self.now = now
    self.chunker = LocalBackgroundAudioChunker(configuration: configuration)
  }

  init(
    language: String,
    plan: LocalTranscriptionPlan,
    configuration: LocalBackgroundChunkerConfiguration = LocalBackgroundChunkerConfiguration(),
    requestHandler: @escaping RequestHandler,
    temporaryDirectory: URL = FileManager.default.temporaryDirectory,
    fileManager: FileManager = .default,
    makeRequestId: @escaping () -> String = { UUID().uuidString },
    now: @escaping () -> Date = Date.init
  ) {
    self.language = language
    self.plan = plan
    self.configuration = configuration
    self.requestHandler = requestHandler
    self.temporaryDirectory = temporaryDirectory
    self.fileManager = fileManager
    self.makeRequestId = makeRequestId
    self.now = now
    self.chunker = LocalBackgroundAudioChunker(configuration: configuration)
  }

  func append(pcmData: Data, startTime: Double) -> LocalBackgroundIngestResult {
    enqueue(chunker.append(pcmData: pcmData, startTime: startTime))
  }

  func finishInput() -> LocalBackgroundIngestResult {
    enqueue(chunker.flush())
  }

  func transcribeNext() async throws -> LocalBackgroundASRRawChunkResult? {
    guard !pendingChunks.isEmpty else { return nil }
    let chunk = pendingChunks.removeFirst()
    guard hasSpeechEnergy(chunk.audioData) else {
      let response = LocalASRTranscriptionResponse(
        requestId: makeRequestId(),
        engine: plan.engine,
        model: plan.model,
        language: language,
        segments: [],
        fixture: false
      )
      let rawResult = LocalBackgroundASRRawChunkResult(
        chunk: chunk,
        response: response,
        remappedSegments: [],
        latencySeconds: 0
      )
      rawChunkResults.append(rawResult)
      return rawResult
    }
    let requestId = makeRequestId()
    let audioURL = temporaryDirectory.appendingPathComponent("\(requestId).pcm")
    try chunk.audioData.write(to: audioURL, options: .atomic)
    defer { try? fileManager.removeItem(at: audioURL) }

    let started = now()
    let response = try await requestHandler(
      LocalASRTranscriptionRequest(
        requestId: requestId,
        audioPath: audioURL.path,
        language: language,
        sampleRate: configuration.sampleRate,
        channels: 1,
        engine: plan.engine,
        model: plan.model,
        fixtureSegments: nil
      )
    )
    let latency = max(0, now().timeIntervalSince(started))
    let remapped = remap(response.segments, chunk: chunk)
    let merged = merger.merge(remapped)
    let rawResult = LocalBackgroundASRRawChunkResult(
      chunk: chunk,
      response: response,
      remappedSegments: remapped,
      latencySeconds: latency
    )
    rawChunkResults.append(rawResult)
    _ = merged
    return rawResult
  }

  func transcribePending() async throws -> [LocalBackgroundASRRawChunkResult] {
    var results: [LocalBackgroundASRRawChunkResult] = []
    while let result = try await transcribeNext() {
      results.append(result)
    }
    return results
  }

  func snapshot() -> LocalBackgroundTranscriptSnapshot {
    LocalBackgroundTranscriptSnapshot(
      rawChunkResults: rawChunkResults,
      mergedSegments: merger.segments
    )
  }

  private func enqueue(_ chunks: [LocalBackgroundAudioChunk]) -> LocalBackgroundIngestResult {
    guard !chunks.isEmpty else {
      return LocalBackgroundIngestResult(
        enqueuedChunks: [],
        droppedChunks: [],
        pendingChunkCount: pendingChunks.count
      )
    }

    pendingChunks.append(contentsOf: chunks)
    var dropped: [LocalBackgroundAudioChunk] = []
    if pendingChunks.count > configuration.maxPendingChunks {
      let overflow = pendingChunks.count - configuration.maxPendingChunks
      dropped = Array(pendingChunks.prefix(overflow))
      pendingChunks.removeFirst(overflow)
      droppedChunkCount += overflow
    }

    return LocalBackgroundIngestResult(
      enqueuedChunks: chunks,
      droppedChunks: dropped,
      pendingChunkCount: pendingChunks.count
    )
  }

  private func remap(
    _ segments: [LocalASRTranscriptSegment],
    chunk: LocalBackgroundAudioChunk
  ) -> [NormalizedTranscriptSegment] {
    segments.map { segment in
      var normalized = segment.normalized()
      normalized.start = chunk.startTime + segment.start
      normalized.end = chunk.startTime + segment.end
      normalized.segmentId = "local-bg-\(chunk.sequence)-\(segment.id ?? "\(segment.start)")"
      return normalized
    }
  }

  private func hasSpeechEnergy(_ audioData: Data) -> Bool {
    var peak = 0
    var sumSquares = 0.0
    var sampleCount = 0

    audioData.withUnsafeBytes { rawBuffer in
      for sample in rawBuffer.bindMemory(to: Int16.self) {
        let magnitude = sample == Int16.min ? Int(Int16.max) : Int(abs(sample))
        peak = max(peak, magnitude)
        sumSquares += Double(magnitude * magnitude)
        sampleCount += 1
      }
    }

    guard sampleCount > 0 else { return false }
    let rms = sqrt(sumSquares / Double(sampleCount))
    return peak >= Int(configuration.speechPeakAmplitudeThreshold)
      && rms >= configuration.speechRMSAmplitudeThreshold
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
  enum Route: Equatable {
    case cloudBackend(fallbackReason: String?)
    case localWhisper(LocalTranscriptionPlan)
    case unavailable(String)
  }

  var route: Route

  var useCloudBackend: Bool {
    if case .cloudBackend = route {
      return true
    }
    return false
  }

  var requiresCloudEntitlement: Bool {
    useCloudBackend
  }

  var localPlan: LocalTranscriptionPlan? {
    if case .localWhisper(let plan) = route {
      return plan
    }
    return nil
  }

  var unsupportedLocalReason: String? {
    switch route {
    case .cloudBackend(let fallbackReason):
      return fallbackReason
    case .localWhisper:
      return nil
    case .unavailable(let reason):
      return reason
    }
  }
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
        route: .unavailable(resolved.fallbackReason ?? "No local transcription engine is available")
      )
    }

    guard resolved.provider == .local else {
      return BackgroundTranscriptionRoutingDecision(
        route: .cloudBackend(fallbackReason: resolved.fallbackReason)
      )
    }

    guard let plan = resolved.localPlan else {
      return BackgroundTranscriptionRoutingDecision(
        route: .unavailable("No local transcription engine is available")
      )
    }

    return BackgroundTranscriptionRoutingDecision(route: .localWhisper(plan))
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
