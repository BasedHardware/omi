import FluidAudio
import Foundation
import OmiSupport

/// Recognizes words, with times on the audio's clock, from a local audio file.
protocol CaptureWordRecognizing: Sendable {
  func recognizeWords(in audioURL: URL) async throws -> [RecognizedWord]
}

/// Fetches a capture's signed audio URL to a local file the recognizer can read.
protocol CaptureAudioFetching: Sendable {
  func download(_ remoteURL: URL) async throws -> URL
}

enum CaptureTranscriptResyncError: LocalizedError, Equatable {
  case noAudio
  case nothingRecognized
  case tooFewMatches(matched: Int, alignable: Int)

  var errorDescription: String? {
    switch self {
    case .noAudio:
      return "Audio is not ready to sync against."
    case .nothingRecognized:
      return "No speech was recognized in the audio."
    case .tooFewMatches(let matched, let alignable):
      return "Only \(matched) of \(alignable) sentences were found in the audio; the transcript was left as is."
    }
  }
}

/// On-device recognition with the Parakeet model the app already ships for
/// live transcription. Models load once per process and stay resident so a
/// second resync starts immediately.
actor ParakeetCaptureWordRecognizer: CaptureWordRecognizing {
  static let shared = ParakeetCaptureWordRecognizer()

  private var manager: AsrManager?

  private func loadedManager() async throws -> AsrManager {
    if let manager { return manager }
    // v3 is multilingual and is the variant the live transcriber caches on
    // this machine; loading it never triggers a second download.
    let models = try await AsrModels.downloadAndLoad(version: .v3)
    let manager = AsrManager()
    try await manager.loadModels(models)
    self.manager = manager
    return manager
  }

  func recognizeWords(in audioURL: URL) async throws -> [RecognizedWord] {
    let manager = try await loadedManager()
    var decoderState = TdtDecoderState.make()
    let result = try await manager.transcribe(audioURL, decoderState: &decoderState, language: nil)
    let timings = buildWordTimings(from: result.tokenTimings ?? [])
    return timings.map { RecognizedWord(text: $0.word, start: $0.startTime) }
  }
}

struct URLSessionCaptureAudioFetcher: CaptureAudioFetching {
  func download(_ remoteURL: URL) async throws -> URL {
    let (temporary, _) = try await URLSession.shared.download(from: remoteURL)
    // Keep the extension AVFoundation sniffs; the download lands nameless.
    let destination = FileManager.default.temporaryDirectory
      .appendingPathComponent("capture-resync-\(UUID().uuidString)")
      .appendingPathExtension(remoteURL.pathExtension.isEmpty ? "wav" : remoteURL.pathExtension)
    try? FileManager.default.removeItem(at: destination)
    try FileManager.default.moveItem(at: temporary, to: destination)
    return destination
  }
}

/// A completed sync, kept locally so reopening the capture shows the corrected
/// transcript without listening again. Keyed by the audio part it was aligned
/// against; a re-merged file invalidates it.
struct CaptureTranscriptSyncRecord: Codable, Equatable {
  struct SegmentTiming: Codable, Equatable {
    let start: TimeInterval
    let end: TimeInterval
  }

  let audioFileID: String
  let startedAt: TimeInterval
  let timings: [String: SegmentTiming]
  let matchedSegments: Int
  let alignableSegments: Int
  let shiftAtStart: TimeInterval
  let shiftAtEnd: TimeInterval

  var report: CaptureTranscriptSyncReport {
    CaptureTranscriptSyncReport(
      matchedSegments: matchedSegments, alignableSegments: alignableSegments,
      shiftAtStart: shiftAtStart, shiftAtEnd: shiftAtEnd)
  }
}

struct CaptureTranscriptSyncStore {
  static let keyPrefix = "captureTranscriptSync."
  static let indexKey = "captureTranscriptSync.index"
  static let capacity = 100

  let defaults: UserDefaults

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
  }

  func record(for conversationID: String) -> CaptureTranscriptSyncRecord? {
    guard let data = defaults.data(forKey: Self.keyPrefix + conversationID) else { return nil }
    return try? JSONDecoder().decode(CaptureTranscriptSyncRecord.self, from: data)
  }

  func save(_ record: CaptureTranscriptSyncRecord, for conversationID: String) {
    guard let data = try? JSONEncoder().encode(record) else { return }
    defaults.set(data, forKey: Self.keyPrefix + conversationID)
    var index = (defaults.stringArray(forKey: Self.indexKey) ?? []).filter { $0 != conversationID }
    index.append(conversationID)
    while index.count > Self.capacity {
      let evicted = index.removeFirst()
      defaults.removeObject(forKey: Self.keyPrefix + evicted)
    }
    defaults.set(index, forKey: Self.indexKey)
  }

  func remove(for conversationID: String) {
    defaults.removeObject(forKey: Self.keyPrefix + conversationID)
    let index = (defaults.stringArray(forKey: Self.indexKey) ?? []).filter { $0 != conversationID }
    defaults.set(index, forKey: Self.indexKey)
  }

  /// The stored sync applied to a freshly loaded conversation, or nil when
  /// there is none or it was made against a different audio part.
  func applied(to conversation: ServerConversation) -> ServerConversation? {
    guard let record = record(for: conversation.id),
      conversation.audioFiles.count == 1,
      conversation.audioFiles.first?.id == record.audioFileID
    else { return nil }
    let segments = conversation.transcriptSegments.map { segment -> TranscriptSegment in
      guard let timing = record.timings[segment.backendId ?? segment.id] else { return segment }
      return segment.retimed(start: timing.start, end: timing.end)
    }
    return conversation.onAudioClock(segments: segments, startedAt: Date(timeIntervalSince1970: record.startedAt))
  }
}

extension TranscriptSegment {
  func retimed(start: TimeInterval, end: TimeInterval) -> TranscriptSegment {
    TranscriptSegment(
      id: id, backendId: backendId, text: text, speaker: speaker, isUser: isUser, personId: personId,
      start: start, end: end, translations: translations)
  }
}

extension ServerConversation {
  /// The same conversation with its transcript on the audio's clock: segment
  /// times are seconds into the media and `startedAt` is when the media begins.
  func onAudioClock(segments: [TranscriptSegment], startedAt: Date) -> ServerConversation {
    ServerConversation(
      id: id, createdAt: createdAt, updatedAt: updatedAt, startedAt: startedAt, finishedAt: finishedAt,
      structured: structured, transcriptSegments: segments, transcriptSegmentsIncluded: transcriptSegmentsIncluded,
      geolocation: geolocation, photos: photos, appsResults: appsResults, source: source, language: language,
      audioFiles: audioFiles, conversationAudio: conversationAudio, status: status, discarded: discarded,
      deleted: deleted, isLocked: isLocked, starred: starred, folderId: folderId, inputDeviceName: inputDeviceName,
      deferred: deferred)
  }
}

/// Drives one resync: fetch the audio, listen to it on-device, align the
/// transcript, and hand back a conversation whose transcript sits on the
/// audio's clock. Speaker labels and person assignments are never touched.
@MainActor
final class CaptureTranscriptResyncer: ObservableObject {
  enum Phase: Equatable {
    case idle
    case downloading
    case listening
    case aligning
    case synced(CaptureTranscriptSyncReport)
    case failed(String)

    var isBusy: Bool {
      switch self {
      case .downloading, .listening, .aligning: return true
      case .idle, .synced, .failed: return false
      }
    }
  }

  @Published private(set) var phase: Phase = .idle

  private let recognizer: any CaptureWordRecognizing
  private let fetcher: any CaptureAudioFetching
  private let store: CaptureTranscriptSyncStore

  init(
    recognizer: any CaptureWordRecognizing = ParakeetCaptureWordRecognizer.shared,
    fetcher: any CaptureAudioFetching = URLSessionCaptureAudioFetcher(),
    store: CaptureTranscriptSyncStore = CaptureTranscriptSyncStore()
  ) {
    self.recognizer = recognizer
    self.fetcher = fetcher
    self.store = store
  }

  func reset() {
    phase = .idle
  }

  /// Returns the corrected conversation, or nil (with `phase == .failed`)
  /// when the audio could not be matched confidently enough to move anything.
  func resync(
    conversation: ServerConversation,
    artifact: CapturePlaybackArtifact
  ) async -> ServerConversation? {
    guard !phase.isBusy else { return nil }
    guard let firstSpan = artifact.spans.first, let startedAt = conversation.startedAt,
      let audioFileID = conversation.audioFiles.first?.id
    else {
      phase = .failed(CaptureTranscriptResyncError.noAudio.localizedDescription)
      return nil
    }

    phase = .downloading
    let localURL: URL
    do {
      localURL = try await fetcher.download(artifact.signedURL)
    } catch {
      phase = .failed("Couldn't download the audio: \(error.localizedDescription)")
      return nil
    }
    defer { try? FileManager.default.removeItem(at: localURL) }

    phase = .listening
    let words: [RecognizedWord]
    do {
      words = try await recognizer.recognizeWords(in: localURL)
    } catch {
      phase = .failed("On-device recognition failed: \(error.localizedDescription)")
      return nil
    }
    guard !words.isEmpty else {
      phase = .failed(CaptureTranscriptResyncError.nothingRecognized.localizedDescription)
      return nil
    }

    phase = .aligning
    let segments = conversation.transcriptSegments
    let matches = CaptureTranscriptAlignmentPolicy.matches(segments: segments, words: words)
    guard let curve = CaptureTranscriptAlignmentPolicy.offsetCurve(from: matches) else {
      let alignable = segments.filter {
        CaptureTranscriptAlignmentPolicy.normalizedTokens($0.text).count >= CaptureTranscriptAlignmentPolicy.gramSize
      }.count
      phase = .failed(
        CaptureTranscriptResyncError.tooFewMatches(matched: matches.count, alignable: alignable).localizedDescription)
      return nil
    }
    let rebased = CaptureTranscriptAlignmentPolicy.rebase(segments: segments, curve: curve)
    let report = CaptureTranscriptAlignmentPolicy.report(segments: segments, matches: matches, curve: curve)
    // Media time zero is the first span's wall offset on the old clock.
    let mediaStart = startedAt.addingTimeInterval(firstSpan.wallOffset - firstSpan.artifactOffset)
    let synced = conversation.onAudioClock(segments: rebased, startedAt: mediaStart)

    store.save(
      CaptureTranscriptSyncRecord(
        audioFileID: audioFileID,
        startedAt: mediaStart.timeIntervalSince1970,
        timings: Dictionary(
          lastWriteWins: rebased.map { ($0.backendId ?? $0.id, .init(start: $0.start, end: $0.end)) }),
        matchedSegments: report.matchedSegments,
        alignableSegments: report.alignableSegments,
        shiftAtStart: report.shiftAtStart,
        shiftAtEnd: report.shiftAtEnd
      ),
      for: conversation.id
    )
    phase = .synced(report)
    return synced
  }
}
