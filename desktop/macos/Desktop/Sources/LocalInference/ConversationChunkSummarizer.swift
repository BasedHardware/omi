import Foundation

/// Chunk-map-reduce summarizer over local GRDB segments (S10).
///
/// Window-agnostic: the selected engine reports `contextWindowTokens`. A
/// single-chunk transcript skips the map pass. Fail-closed through
/// `LocalInferenceRuntime` — never a cloud LLM. A stored projection whose
/// `transcript_sha256` still matches is returned as-is; retry never regenerates.
struct ConversationChunkSummarizer: Sendable {
  var runtime: LocalInferenceRuntime
  var store: any LocalProjectionStoring
  var now: @Sendable () -> Date
  var deviceClass: String
  var sourceLabel: String
  var timeZone: TimeZone

  init(
    runtime: LocalInferenceRuntime,
    store: any LocalProjectionStoring,
    now: @escaping @Sendable () -> Date = { Date() },
    deviceClass: String = ClientProcessingContract.defaultDeviceClass,
    sourceLabel: String = "Recording",
    timeZone: TimeZone = .current
  ) {
    self.runtime = runtime
    self.store = store
    self.now = now
    self.deviceClass = deviceClass
    self.sourceLabel = sourceLabel
    self.timeZone = timeZone
  }

  func summarize(
    sessionId: Int64,
    segments: [TranscriptHash.Segment],
    startedAt: Date
  ) async throws -> StoredClientProjection {
    let digest = TranscriptHash.sha256(segments: segments)
    if let stored = try await store.load(sessionId: sessionId), stored.transcriptSha256 == digest {
      return stored
    }

    let minimumInput = DeterministicMinimumInput(
      transcript: Self.minimumTranscript(segments),
      startedAt: startedAt,
      sourceLabel: sourceLabel,
      timeZone: timeZone
    )
    let generatedAt = now()
    let projection: OmiAPI.ClientProcessing
    if let window = runtime.selectedContextWindowTokens() {
      let draft = await generateDraft(segments: segments, window: window, minimumInput: minimumInput)
      projection = Self.projection(
        from: draft,
        digest: digest,
        minimumInput: minimumInput,
        generatedAt: generatedAt,
        deviceClass: deviceClass
      )
    } else {
      let generation: LocalInferenceGeneration<LocalSummaryDraft> = await runtime.generateStructuredFailClosed(
        prompt: Self.finalPrompt(Self.plainTranscript(segments)),
        schema: LocalSummaryDraft.jsonSchema,
        minimumInput: minimumInput
      )
      projection = Self.projection(
        from: generation,
        digest: digest,
        minimumInput: minimumInput,
        generatedAt: generatedAt,
        deviceClass: deviceClass
      )
    }

    let stored = try ClientProcessingContract.stored(projection)
    try await store.save(sessionId: sessionId, projection: stored)
    return stored
  }

  private func generateDraft(
    segments: [TranscriptHash.Segment],
    window: Int,
    minimumInput: DeterministicMinimumInput
  ) async -> LocalInferenceGeneration<LocalSummaryDraft> {
    let groups = Self.chunk(segments, windowTokens: window)
    if groups.count <= 1 {
      return await runtime.generateStructuredFailClosed(
        prompt: Self.finalPrompt(Self.plainTranscript(segments)),
        schema: LocalSummaryDraft.jsonSchema,
        minimumInput: minimumInput
      )
    }

    var partials: [LocalSummaryDraft] = []
    partials.reserveCapacity(groups.count)
    for (index, group) in groups.enumerated() {
      let generation: LocalInferenceGeneration<LocalSummaryDraft> = await runtime.generateStructuredFailClosed(
        prompt: Self.mapPrompt(Self.plainTranscript(group), index: index + 1, total: groups.count),
        schema: LocalSummaryDraft.jsonSchema,
        minimumInput: minimumInput
      )
      switch generation {
      case .engine(let draft, _):
        partials.append(draft)
      case .deterministicMinimum:
        return generation
      }
    }

    return await runtime.generateStructuredFailClosed(
      prompt: Self.reducePrompt(partials),
      schema: LocalSummaryDraft.jsonSchema,
      minimumInput: minimumInput
    )
  }

  static func projection(
    from generation: LocalInferenceGeneration<LocalSummaryDraft>,
    digest: String,
    minimumInput: DeterministicMinimumInput,
    generatedAt: Date,
    deviceClass: String
  ) -> OmiAPI.ClientProcessing {
    switch generation {
    case .engine(let draft, let engineID):
      let minimum = DeterministicConversationMinimum.make(from: minimumInput)
      return ClientProcessingContract.assemble(
        draft: draft,
        transcriptSha256: digest,
        provenance: OmiAPI.ProjectionProvenance(
          deviceClass: deviceClass,
          generatedAt: ClientProcessingContract.iso8601(generatedAt),
          modelId: engineID.rawValue,
          runtime: ClientProcessingContract.localRuntime
        ),
        fallbackTitle: minimum.title
      )
    case .deterministicMinimum(let minimum):
      return ClientProcessingContract.assembleMinimum(
        minimum,
        transcriptSha256: digest,
        generatedAt: generatedAt,
        deviceClass: deviceClass
      )
    }
  }

  /// UTF-8 bytes / 4, matching the usual tokenizer underestimate so a chunk
  /// that fits this budget also fits the real window.
  static func estimatedTokens(_ text: String) -> Int {
    max(1, (text.utf8.count + 3) / 4)
  }

  static func chunk(
    _ segments: [TranscriptHash.Segment],
    windowTokens: Int
  ) -> [[TranscriptHash.Segment]] {
    guard !segments.isEmpty else { return [[]] }
    let wrapper = estimatedTokens(mapPrompt("", index: 1, total: 1))
    let budget = max(windowTokens - wrapper - 8, 64)
    var groups: [[TranscriptHash.Segment]] = []
    var current: [TranscriptHash.Segment] = []
    var currentTokens = 0

    func flush() {
      if !current.isEmpty {
        groups.append(current)
        current = []
        currentTokens = 0
      }
    }

    for segment in segments {
      let piece = estimatedTokens(plainTranscript([segment]))
      if piece > budget {
        flush()
        groups.append(contentsOf: splitSegment(segment, budget: budget))
        continue
      }
      if !current.isEmpty, currentTokens + piece > budget {
        flush()
      }
      current.append(segment)
      currentTokens += piece
    }
    flush()
    return groups.isEmpty ? [[]] : groups
  }

  private static func splitSegment(
    _ segment: TranscriptHash.Segment,
    budget: Int
  ) -> [[TranscriptHash.Segment]] {
    let text = segment.text
    guard !text.isEmpty else { return [[segment]] }
    var parts: [[TranscriptHash.Segment]] = []
    var start = text.startIndex
    while start < text.endIndex {
      var end = start
      var accepted = start
      while end < text.endIndex {
        let candidate = String(text[start...end])
        var piece = segment
        piece.text = candidate
        if estimatedTokens(plainTranscript([piece])) > budget {
          break
        }
        accepted = text.index(after: end)
        end = accepted
      }
      if accepted == start {
        accepted = text.index(after: start)
      }
      var piece = segment
      piece.text = String(text[start..<accepted])
      parts.append([piece])
      start = accepted
    }
    return parts
  }

  static func minimumTranscript(_ segments: [TranscriptHash.Segment]) -> String {
    segments.map { $0.text.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
      .joined(separator: " ")
  }

  static func plainTranscript(_ segments: [TranscriptHash.Segment]) -> String {
    segments.map { segment in
      let trimmed = segment.speaker?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      let label = trimmed.isEmpty ? TranscriptHash.defaultSpeaker : trimmed
      return "\(label): \(segment.text)"
    }.joined(separator: "\n")
  }

  static func mapPrompt(_ transcript: String, index: Int, total: Int) -> String {
    """
    Summarize chunk \(index) of \(total) of a conversation. Return title, overview, sections, and action items. Do not invent facts.

    Transcript:
    \(transcript)
    """
  }

  static func finalPrompt(_ transcript: String) -> String {
    """
    Summarize this conversation. Return title, overview, sections, and action items. Do not invent facts.

    Transcript:
    \(transcript)
    """
  }

  static func reducePrompt(_ partials: [LocalSummaryDraft]) -> String {
    let body = partials.enumerated().map { index, draft in
      let actions = draft.actionItems.map(\.description).joined(separator: "; ")
      return "Chunk \(index + 1): \(draft.title)\n\(draft.overview)\nActions: \(actions)"
    }.joined(separator: "\n\n")
    return """
      Merge these chunk summaries into one conversation summary. Return title, overview, sections, and action items. Do not invent facts.

      \(body)
      """
  }
}
