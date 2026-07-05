import Foundation
import FluidAudio
import NaturalLanguage

/// Per-turn spoken-language identification for push-to-talk.
///
/// The realtime providers transcribe PTT audio with per-utterance language auto-detect,
/// which regularly mislabels short utterances (Russian rendered as Italian). This service
/// answers "which of the USER'S languages is this turn most likely in?" fast enough to
/// hint the provider before the turn commits:
///
///   • decode the (partial) turn buffer with the multilingual Parakeet v3 model that
///     ships with the app (~100× realtime on Apple Neural Engine, so ~25ms for 2.5s), then
///   • run Apple's NLLanguageRecognizer on the text, biased toward the user's languages.
///
/// This deliberately does NOT touch the ambient transcription pipeline — it holds its own
/// AsrManager (always v3/multilingual; the ambient one is v2/English-only for `en` users)
/// and only ever decodes PTT turn buffers handed to it.
actor PTTLanguageIdentifier {
  static let shared = PTTLanguageIdentifier()

  struct Verdict {
    /// Base ISO 639-1 code of the detected language, nil when nothing reliable was heard.
    let languageCode: String?
    /// The local transcript the detection ran on (used as the bubble fallback when the
    /// provider transcript comes back in a language outside the user's set).
    let transcript: String?
  }

  private var manager: AsrManager?
  private var loadTask: Task<AsrManager?, Never>?

  /// Load the multilingual model off the critical path (called when the hub warms up)
  /// so the first PTT turn doesn't pay the model-load latency.
  func prewarm() async {
    _ = await loadedManager()
  }

  private func loadedManager() async -> AsrManager? {
    if let manager { return manager }
    if let loadTask { return await loadTask.value }
    let task = Task<AsrManager?, Never> {
      do {
        let started = Date()
        let models = try await AsrModels.downloadAndLoad(version: .v3)
        let m = AsrManager()
        try await m.loadModels(models)
        log(
          "PTTLanguageIdentifier: Parakeet v3 ready in \(String(format: "%.1f", Date().timeIntervalSince(started)))s"
        )
        return m
      } catch {
        logError("PTTLanguageIdentifier: model load failed", error: error)
        return nil
      }
    }
    loadTask = task
    let m = await task.value
    manager = m
    loadTask = nil
    return m
  }

  /// Identify the language of a PTT turn buffer (16 kHz mono s16le PCM).
  /// - Parameters:
  ///   - pcm16k: turn audio; may be a partial buffer (early hint) or the full turn.
  ///   - candidates: the user's base language codes (["ru", "en"]); biases detection and
  ///     gates the verdict — a dominant language OUTSIDE the set yields `languageCode` nil
  ///     ("no match → let the provider decide"), while the transcript is still returned.
  ///   - clipSeconds: optionally decode only the first N seconds (early hint path).
  func identify(pcm16k: Data, candidates: [String], clipSeconds: Double? = nil) async -> Verdict {
    guard let manager = await loadedManager() else { return Verdict(languageCode: nil, transcript: nil) }
    var samples = Self.int16ToFloat32(pcm16k)
    if let clipSeconds {
      samples = Array(samples.prefix(Int(clipSeconds * 16_000)))
    }
    // Below ~0.4s there isn't enough speech for either the decoder or the detector.
    guard samples.count >= 6_400 else { return Verdict(languageCode: nil, transcript: nil) }

    do {
      var ds = try TdtDecoderState()
      let started = Date()
      let result = try await manager.transcribe(samples, decoderState: &ds, language: nil)
      // The TDT decoder emits literal "<unk>" for out-of-vocabulary tokens (slangy
      // vowels etc.) — never show that in a chat bubble.
      let text = result.text
        .replacingOccurrences(of: "<unk>", with: "")
        .replacingOccurrences(of: "  ", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard text.contains(where: { $0.isLetter }) else {
        return Verdict(languageCode: nil, transcript: nil)
      }
      let code = Self.detectLanguage(of: text, candidates: candidates)
      log(
        "PTTLanguageIdentifier: \(String(format: "%.1f", Double(samples.count) / 16_000))s → "
          + "lang=\(code ?? "none") in \(Int(Date().timeIntervalSince(started) * 1000))ms"
      )
      return Verdict(languageCode: code, transcript: text)
    } catch {
      logError("PTTLanguageIdentifier: decode failed", error: error)
      return Verdict(languageCode: nil, transcript: nil)
    }
  }

  /// Text-level language detection, biased toward (but not constrained to) `candidates`.
  /// Returns the base code only when the dominant language IS one of the candidates —
  /// anything else means "no match" and the caller leaves the provider on auto-detect.
  nonisolated static func detectLanguage(of text: String, candidates: [String]) -> String? {
    guard let base = dominantLanguage(of: text, hints: candidates) else { return nil }
    guard candidates.isEmpty || candidates.contains(base) else { return nil }
    return base
  }

  /// Ungated dominant-language detection, biased toward `hints`. Used to classify the
  /// PROVIDER transcript at turn-done: the bias keeps code-switched utterances ("play
  /// Despacito") classified into the user's set, so a correct provider transcript isn't
  /// swapped for a lower-quality local one.
  nonisolated static func dominantLanguage(of text: String, hints: [String]) -> String? {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.count >= 3 else { return nil }
    let recognizer = NLLanguageRecognizer()
    if !hints.isEmpty {
      var weights: [NLLanguage: Double] = [:]
      for code in hints { weights[NLLanguage(rawValue: nlCode(for: code))] = 0.3 }
      recognizer.languageHints = weights
    }
    recognizer.processString(trimmed)
    guard let dominant = recognizer.dominantLanguage else { return nil }
    return normalizedBaseCode(dominant.rawValue)
  }

  /// NLLanguage's ISO codes differ from our settings codes in places ("nb" vs "no").
  private nonisolated static let nlToSettingsCode: [String: String] = ["nb": "no"]
  private nonisolated static let settingsToNLCode: [String: String] = ["no": "nb"]

  nonisolated static func normalizedBaseCode(_ raw: String) -> String {
    let base = AssistantSettings.baseLanguageCode(raw)
    return nlToSettingsCode[base] ?? base
  }

  private nonisolated static func nlCode(for settingsCode: String) -> String {
    settingsToNLCode[settingsCode] ?? settingsCode
  }

  private nonisolated static func int16ToFloat32(_ data: Data) -> [Float] {
    let count = data.count / 2
    guard count > 0 else { return [] }
    return data.withUnsafeBytes { raw -> [Float] in
      let int16 = raw.bindMemory(to: Int16.self)
      var floats = [Float](repeating: 0, count: count)
      for i in 0..<count {
        floats[i] = Float(Int16(littleEndian: int16[i])) / 32768.0
      }
      return floats
    }
  }
}
