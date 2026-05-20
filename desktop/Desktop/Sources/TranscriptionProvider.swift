import Darwin
import Foundation

enum TranscriptionProviderKind: String, CaseIterable, Codable, Equatable {
  case auto
  case local
  case cloud
}

enum TranscriptionQualityPreset: String, CaseIterable, Codable, Equatable {
  case auto
  case fast
  case balanced
  case accurate
}

enum LocalTranscriptionEngine: String, CaseIterable, Codable, Equatable, Hashable {
  case mlxWhisper = "mlx-whisper"
  case fasterWhisper = "faster-whisper"
}

struct TranscriptionProviderSelection: Codable, Equatable {
  var mode: TranscriptionProviderKind
  var quality: TranscriptionQualityPreset

  static let `default` = TranscriptionProviderSelection(mode: .auto, quality: .auto)
}

struct LocalTranscriptionCapabilities: Equatable {
  enum Processor: Equatable {
    case nativeAppleSilicon
    case rosettaOnAppleSilicon
    case intel
    case unknown
  }

  var processor: Processor
  var physicalMemoryBytes: UInt64
  var availableEngines: Set<LocalTranscriptionEngine>

  var isNativeAppleSilicon: Bool {
    processor == .nativeAppleSilicon
  }

  var canUseMLXWhisper: Bool {
    isNativeAppleSilicon && availableEngines.contains(.mlxWhisper)
  }

  var canUseFasterWhisper: Bool {
    availableEngines.contains(.fasterWhisper)
  }

  var canUseAnyLocalEngine: Bool {
    canUseMLXWhisper || canUseFasterWhisper
  }
}

struct LocalTranscriptionCapabilityDetector {
  var physicalMemoryBytes: () -> UInt64 = { ProcessInfo.processInfo.physicalMemory }
  var isTranslatedProcess: () -> Bool = {
    var translated: Int32 = 0
    var size = MemoryLayout<Int32>.size
    let result = sysctlbyname("sysctl.proc_translated", &translated, &size, nil, 0)
    return result == 0 && translated == 1
  }
  var availableEngines: () -> Set<LocalTranscriptionEngine> = { [] }

  func detect() -> LocalTranscriptionCapabilities {
    LocalTranscriptionCapabilities(
      processor: detectProcessor(),
      physicalMemoryBytes: physicalMemoryBytes(),
      availableEngines: availableEngines()
    )
  }

  private func detectProcessor() -> LocalTranscriptionCapabilities.Processor {
    #if arch(arm64)
      return isTranslatedProcess() ? .rosettaOnAppleSilicon : .nativeAppleSilicon
    #elseif arch(x86_64)
      return isTranslatedProcess() ? .rosettaOnAppleSilicon : .intel
    #else
      return .unknown
    #endif
  }
}

struct TranscriptionProviderPolicyResult: Equatable {
  var provider: TranscriptionProviderKind
  var quality: TranscriptionQualityPreset
  var localEngine: LocalTranscriptionEngine?
  var localPlan: LocalTranscriptionPlan?
  var fallbackReason: String?

  var usesCloud: Bool {
    provider == .cloud
  }

  var usesLocal: Bool {
    provider == .local
  }
}

struct TranscriptionProviderPolicy {
  func resolve(
    selection: TranscriptionProviderSelection,
    capabilities: LocalTranscriptionCapabilities
  ) -> TranscriptionProviderPolicyResult {
    let quality = selection.quality

    switch selection.mode {
    case .cloud:
      return TranscriptionProviderPolicyResult(
        provider: .cloud, quality: quality, localEngine: nil, localPlan: nil, fallbackReason: nil)
    case .local:
      if let plan = localPlan(for: quality, capabilities: capabilities) {
        return TranscriptionProviderPolicyResult(
          provider: .local, quality: quality, localEngine: plan.engine, localPlan: plan,
          fallbackReason: nil)
      }
      return TranscriptionProviderPolicyResult(
        provider: .cloud,
        quality: quality,
        localEngine: nil,
        localPlan: nil,
        fallbackReason: "No local transcription engine is available"
      )
    case .auto:
      if let plan = localPlan(for: quality, capabilities: capabilities) {
        return TranscriptionProviderPolicyResult(
          provider: .local, quality: quality, localEngine: plan.engine, localPlan: plan,
          fallbackReason: nil)
      }
      return TranscriptionProviderPolicyResult(
        provider: .cloud,
        quality: quality,
        localEngine: nil,
        localPlan: nil,
        fallbackReason: "Auto mode fell back to cloud because no local engine is available"
      )
    }
  }

  private func localPlan(
    for quality: TranscriptionQualityPreset,
    capabilities: LocalTranscriptionCapabilities
  ) -> LocalTranscriptionPlan? {
    let engine: LocalTranscriptionEngine
    if capabilities.canUseMLXWhisper {
      engine = .mlxWhisper
    } else if capabilities.canUseFasterWhisper {
      engine = .fasterWhisper
    } else {
      return nil
    }

    return LocalTranscriptionPlan(
      engine: engine,
      model: model(for: quality, engine: engine, memoryBytes: capabilities.physicalMemoryBytes),
      quality: quality
    )
  }

  private func model(
    for quality: TranscriptionQualityPreset,
    engine: LocalTranscriptionEngine,
    memoryBytes: UInt64
  ) -> LocalTranscriptionModel {
    let gib = memoryBytes / (1024 * 1024 * 1024)
    switch quality {
    case .fast:
      return .base
    case .balanced, .auto:
      return gib >= 8 ? .small : .base
    case .accurate:
      if engine == .mlxWhisper, gib >= 24 {
        return .largeV3Turbo
      }
      return gib >= 16 ? .medium : .small
    }
  }
}

struct NormalizedTranscriptTranslation: Codable, Equatable {
  var lang: String
  var text: String
}

struct NormalizedTranscriptSegment: Codable, Equatable, Identifiable {
  var id: String { segmentId ?? "\(speaker)-\(start)" }
  var segmentId: String?
  var speaker: Int
  var speakerLabel: String?
  var text: String
  var start: Double
  var end: Double
  var isUser: Bool
  var personId: String?
  var translations: [NormalizedTranscriptTranslation]
}

enum TranscriptionProviderConnectionState: Equatable {
  case idle
  case starting
  case connected
  case stopping
  case stopped
  case failed(String)
}

struct TranscriptionProviderCapabilities: Equatable {
  var provider: TranscriptionProviderKind
  var supportsStreaming: Bool
  var supportsBatch: Bool
  var supportsLocalProcessing: Bool
  var supportsSpeakerDiarization: Bool
  var supportsTranslations: Bool
  var localEngine: LocalTranscriptionEngine?
}

struct TranscriptionProviderEvent {
  var type: String
  var raw: [String: Any]
}

struct TranscriptionProviderCallbacks {
  var onSegments: ([NormalizedTranscriptSegment]) -> Void
  var onEvent: (TranscriptionProviderEvent) -> Void
  var onError: (Error) -> Void
  var onConnected: () -> Void
  var onDisconnected: () -> Void
}

struct TranscriptionProviderConfiguration: Equatable {
  var language: String
  var mode: TranscriptionService.StreamingMode
  var contextKeywords: [String]

  static func conversation(language: String, contextKeywords: [String] = [])
    -> TranscriptionProviderConfiguration
  {
    TranscriptionProviderConfiguration(
      language: language, mode: .conversation, contextKeywords: contextKeywords)
  }
}

protocol TranscriptionProvider: AnyObject {
  var status: TranscriptionProviderConnectionState { get }
  var capabilities: TranscriptionProviderCapabilities { get }
  var failureState: Error? { get }

  func start(
    configuration: TranscriptionProviderConfiguration, callbacks: TranscriptionProviderCallbacks)
  func sendAudio(_ data: Data)
  func finalize()
  func stop()
}

final class CloudTranscriptionProvider: TranscriptionProvider {
  private var service: TranscriptionService?
  private(set) var status: TranscriptionProviderConnectionState = .idle
  private(set) var failureState: Error?

  let capabilities = TranscriptionProviderCapabilities(
    provider: .cloud,
    supportsStreaming: true,
    supportsBatch: true,
    supportsLocalProcessing: false,
    supportsSpeakerDiarization: true,
    supportsTranslations: true,
    localEngine: nil
  )

  func start(
    configuration: TranscriptionProviderConfiguration, callbacks: TranscriptionProviderCallbacks
  ) {
    do {
      status = .starting
      let service = try TranscriptionService(
        language: configuration.language,
        mode: configuration.mode,
        contextKeywords: configuration.contextKeywords
      )
      self.service = service
      service.start(
        onSegments: { callbacks.onSegments($0.map { $0.normalized }) },
        onEvent: {
          callbacks.onEvent(TranscriptionProviderEvent(type: $0.type, raw: $0.raw))
        },
        onError: { [weak self] error in
          self?.failureState = error
          self?.status = .failed(error.localizedDescription)
          callbacks.onError(error)
        },
        onConnected: { [weak self] in
          self?.status = .connected
          callbacks.onConnected()
        },
        onDisconnected: { [weak self] in
          self?.status = .stopped
          callbacks.onDisconnected()
        }
      )
    } catch {
      failureState = error
      status = .failed(error.localizedDescription)
      callbacks.onError(error)
    }
  }

  func sendAudio(_ data: Data) {
    service?.sendAudio(data)
  }

  func finalize() {
    service?.finishStream()
  }

  func stop() {
    status = .stopping
    service?.stop()
    service = nil
    status = .stopped
  }
}

final class LocalWhisperTranscriptionProvider: TranscriptionProvider {
  private(set) var status: TranscriptionProviderConnectionState = .idle
  private(set) var failureState: Error?
  let capabilities: TranscriptionProviderCapabilities

  init(engine: LocalTranscriptionEngine?) {
    self.capabilities = TranscriptionProviderCapabilities(
      provider: .local,
      supportsStreaming: false,
      supportsBatch: true,
      supportsLocalProcessing: true,
      supportsSpeakerDiarization: false,
      supportsTranslations: false,
      localEngine: engine
    )
  }

  func start(
    configuration: TranscriptionProviderConfiguration, callbacks: TranscriptionProviderCallbacks
  ) {
    let error = TranscriptionService.TranscriptionError.webSocketError(
      "Local Whisper provider helper is not implemented in this ticket"
    )
    failureState = error
    status = .failed(error.localizedDescription)
    callbacks.onError(error)
  }

  func sendAudio(_ data: Data) {}

  func finalize() {}

  func stop() {
    status = .stopped
  }
}

struct SpeakerSegmentReducer {
  struct ApplyResult: Equatable {
    var added: Int = 0
    var updated: Int = 0
    var totalSegmentCount: Int = 0
    var totalWordCount: Int = 0
  }

  private(set) var segments: [SpeakerSegment] = []
  private(set) var totalSegmentCount: Int = 0
  private(set) var totalWordCount: Int = 0
  var maxInMemorySegments: Int

  init(maxInMemorySegments: Int) {
    self.maxInMemorySegments = maxInMemorySegments
  }

  mutating func reset() {
    segments = []
    totalSegmentCount = 0
    totalWordCount = 0
  }

  mutating func replaceSegments(_ replacement: [SpeakerSegment]) {
    segments = replacement
    totalWordCount = replacement.reduce(0) { $0 + wordCount($1.text) }
  }

  mutating func apply(_ incomingSegments: [SpeakerSegment]) -> ApplyResult {
    var result = ApplyResult()

    for incoming in incomingSegments where !incoming.text.isEmpty {
      if let segId = incoming.segmentId,
        let existingIdx = segments.firstIndex(where: { $0.segmentId == segId })
      {
        let oldWords = wordCount(segments[existingIdx].text)
        var updated = incoming
        if updated.translations.isEmpty && !segments[existingIdx].translations.isEmpty {
          updated.translations = segments[existingIdx].translations
        }
        segments[existingIdx] = updated
        totalWordCount += wordCount(updated.text) - oldWords
        result.updated += 1
      } else {
        segments.append(incoming)
        totalSegmentCount += 1
        totalWordCount += wordCount(incoming.text)
        result.added += 1
      }
    }

    if segments.count > maxInMemorySegments {
      segments.removeFirst(segments.count - maxInMemorySegments)
    }

    result.totalSegmentCount = totalSegmentCount
    result.totalWordCount = totalWordCount
    return result
  }

  mutating func deleteSegmentIds(_ segmentIds: [String]) -> Int {
    let deletedSegments = segments.filter { segment in
      guard let segmentId = segment.segmentId else { return false }
      return segmentIds.contains(segmentId)
    }
    let deletedWords = deletedSegments.reduce(0) { $0 + wordCount($1.text) }
    totalWordCount = max(0, totalWordCount - deletedWords)
    totalSegmentCount = max(0, totalSegmentCount - deletedSegments.count)
    segments.removeAll { segment in
      guard let segmentId = segment.segmentId else { return false }
      return segmentIds.contains(segmentId)
    }
    return deletedSegments.count
  }

  private func wordCount(_ text: String) -> Int {
    text.split(separator: " ").count
  }
}

extension TranscriptionService.BackendSegment {
  var normalized: NormalizedTranscriptSegment {
    NormalizedTranscriptSegment(
      segmentId: id,
      speaker: speaker_id ?? 0,
      speakerLabel: speaker,
      text: text,
      start: start,
      end: end,
      isUser: is_user,
      personId: person_id,
      translations: (translations ?? []).map {
        NormalizedTranscriptTranslation(lang: $0.lang, text: $0.text)
      }
    )
  }
}
