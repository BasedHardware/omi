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
        deviceClass: deviceClass,
        fallback: runtime.fallback
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
        deviceClass: deviceClass,
        fallback: runtime.fallback
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
        schema: LocalSummaryDraft.mapJSONSchema,
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
      prompt: Self.reducePrompt(partials, windowTokens: window),
      schema: LocalSummaryDraft.jsonSchema,
      minimumInput: minimumInput
    )
  }

  static func projection(
    from generation: LocalInferenceGeneration<LocalSummaryDraft>,
    digest: String,
    minimumInput: DeterministicMinimumInput,
    generatedAt: Date,
    deviceClass: String,
    fallback: (any LocalInferenceFallbackRecording)? = nil
  ) -> OmiAPI.ClientProcessing {
    switch generation {
    case .engine(let draft, let engineID):
      let minimum = DeterministicConversationMinimum.make(from: minimumInput)
      let assembled = ClientProcessingContract.assemble(
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
      // A draft can satisfy the schema and still say nothing: every field on
      // `LocalSummaryDraft` decodes through `decodeIfPresent ?? ""` / `?? []`,
      // so `{"title": "Summary"}` is a well-formed draft. Constrained decoding
      // is what normally prevents that, and it is exactly what fails open --
      // llama.cpp has shipped a build that accepted a JSON schema, returned
      // HTTP 200, and generated unconstrained anyway. An empty projection is
      // worse than none: it carries a model id and, because a free-tier
      // conversation's canonical structure is itself the minimum, it is
      // selected over that minimum for display. Fail closed to the minimum.
      guard ClientProcessingContract.carriesContent(assembled) else {
        fallback?.recordLocalInferenceFallback(
          from: engineID.rawValue,
          to: ClientProcessingContract.deterministicModelID,
          reason: "contentless_projection",
          outcome: .degraded
        )
        return ClientProcessingContract.assembleMinimum(
          minimum,
          transcriptSha256: digest,
          generatedAt: generatedAt,
          deviceClass: deviceClass
        )
      }
      return assembled
    case .deterministicMinimum(let minimum):
      return ClientProcessingContract.assembleMinimum(
        minimum,
        transcriptSha256: digest,
        generatedAt: generatedAt,
        deviceClass: deviceClass
      )
    }
  }

  /// Tokens held back from every chunk for the model's own answer.
  ///
  /// A `LanguageModelSession`'s transcript is prompt **plus** completion against
  /// one window, so this is not slack — it is the other half of the budget.
  ///
  /// 1024 was too small. Measured on live AFM, a map pass emitted 7 sections and
  /// 26 action items; a full `LocalSummaryDraft` at the schema's now-bounded caps
  /// (8 sections, 15 action items, 6 events) still runs to well over a thousand
  /// tokens. The failure showed up as `"The session's transcript exceeded the
  /// model's context size."` on prompts that had room, which is why it looked
  /// unrelated to prompt size and therefore non-deterministic.
  ///
  /// 2048 was too small as well, and in a way that hid. Measured 2026-09-21 on live
  /// AFM once the schema generated in authored order: the *same* map prompt
  /// (18.3 KB) produced completions of 3.0 KB, 5.2 KB, 7.0 KB and 10.1 KB. The
  /// large draws threw `"The session's transcript exceeded the model's context
  /// size."` — at nominal thermal state, so not load — and the identical call
  /// succeeded on retry with a small draw, which is why it read as intermittent.
  /// On the real app path one of two long conversations reached the user as a
  /// first-sentence title and nothing else. 3584 covers the largest draft
  /// observed under the full caps at this estimator's bytes/3; the map pass is
  /// additionally held to `LocalSummaryDraft.mapJSONSchema`'s tighter caps,
  /// because a reserve alone cannot bound a completion that has no length limit.
  static let completionReserveTokens = 3584

  /// The reserve actually applied for a window. 3584 is 7/16 of AFM's 8192; on a
  /// window half that size the same absolute reserve would leave ~400 tokens of
  /// transcript per chunk, so smaller windows keep the previous 2048 floor.
  static func completionReserve(windowTokens: Int) -> Int {
    min(completionReserveTokens, max(2048, windowTokens * 7 / 16))
  }

  /// UTF-8 bytes / 3. Deliberately pessimistic; see the caveat below.
  ///
  /// This was bytes / 4, on the "~4 characters per token" rule of thumb, with a
  /// docstring asserting that under-counts so a chunk fitting the budget also
  /// fits the real window. That assertion was never measured, and transcript
  /// text is the wrong shape for it: every turn carries a `SPEAKER_00:` prefix,
  /// several tokens for twelve bytes, and the bodies are dense with names,
  /// numbers and punctuation. Dividing by 3 is the conservative direction.
  ///
  /// **What this does not claim.** AFM failures on long conversations are *not*
  /// established as context overflow, and this change is a mitigation rather
  /// than a fix. Measured 2026-09-18 on an M5 Max running macOS 27, with
  /// `SystemLanguageModel.default.contextSize` reporting 8192:
  ///
  /// - a 7150-token prompt succeeded while a 4975-token one failed
  /// - the same scenario failed end-to-end in one run and succeeded in the next
  /// - failures took 94–163 s before returning, and per-call latency fell from
  ///   ~160 s to ~35 s once the machine had been left idle
  ///
  /// That pattern reads as load or thermal, not as a size boundary. It could not
  /// be diagnosed further because `AFMLocalInferenceAdapter.mapFrameworkError`
  /// flattens every error to `session_failed` under `#available(macOS 27.0, *)` —
  /// so overflow, guardrail refusal, rate limiting and decode failure are
  /// indistinguishable on the OS users actually run.
  ///
  /// Smaller chunks are still the right default while that is true: the cost of
  /// over-estimating is one extra chunk, and the cost of under-estimating is the
  /// whole conversation falling back to the deterministic minimum after minutes
  /// of on-device work.
  static func estimatedTokens(_ text: String) -> Int {
    max(1, (text.utf8.count + 2) / 3)
  }

  static func chunk(
    _ segments: [TranscriptHash.Segment],
    windowTokens: Int
  ) -> [[TranscriptHash.Segment]] {
    guard !segments.isEmpty else { return [[]] }
    let wrapper = estimatedTokens(mapPrompt("", index: 1, total: 1))
    // Reserve room for the answer. A context window covers prompt *and*
    // completion, so sizing a chunk to fill the window leaves the model no
    // tokens to reply in: generation stops at the cap mid-object, the JSON does
    // not parse, and the conversation fail-closes to the deterministic minimum.
    // Measured with an 8-token slack: truncations on 12 of 22 generations, and
    // the first map chunk failing meant 19 of 20 conversations produced nothing.
    // A full LocalSummaryDraft -- title, overview, sections, action items --
    // runs to several hundred tokens, so the reserve has to be of that order.
    let budget = max(windowTokens - wrapper - completionReserve(windowTokens: windowTokens), 64)
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

  /// Extract from one slice of the transcript.
  ///
  /// `index` and `total` are accepted for the chunker's own bookkeeping but are
  /// deliberately kept out of the text: a small model told it is reading "chunk
  /// 2 of 2" titles the result "Summary of Chunk 2 of 2", and that string
  /// reaches the user as their conversation title. What this pass needs is the
  /// facts; the title is decided once, in the reduce.
  static func mapPrompt(_ transcript: String, index: Int, total: Int) -> String {
    _ = (index, total)
    return """
      Extract what was decided, discussed, and committed to in this part of a conversation. Put each distinct topic in its own section, and every commitment someone made in action items. Quote specifics - names, dates, numbers - rather than describing them. Do not invent facts.

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

  /// Fold the chunk drafts into one summary.
  ///
  /// The per-chunk `sections` carry the detail the map pass extracted. Dropping
  /// them here discarded that detail *before* the model saw it, so no model
  /// could retain it however capable: measured retention was 0/20 for one model
  /// and 2/20 for another, which read as a capability ceiling and was not one.
  ///
  /// Chunk indices are deliberately absent. Told it is merging "chunk 2 of 2",
  /// a small model titles the conversation "Chapter 2 of 2"; given an
  /// instruction sentence, it echoes that sentence as the title. Both were
  /// observed as user-visible titles.
  /// `windowTokens` bounds the prompt. The reduce input is the concatenation of
  /// every partial, so it grows with the number of chunks and had no bound at
  /// all: it fit only because long conversations happened to make two or three
  /// chunks. When it does not fit, each partial is cut to an equal share rather
  /// than the tail being dropped, because a meeting's last slice is where the
  /// decisions usually are. Within a partial the order is overview, commitments,
  /// then section detail, so a cut costs detail before it costs a commitment.
  static func reducePrompt(_ partials: [LocalSummaryDraft], windowTokens: Int? = nil) -> String {
    var notes: [[String]] = partials.map { draft in
      var lines: [String] = []
      if !draft.overview.isEmpty { lines.append(draft.overview) }
      for action in draft.actionItems where !action.description.isEmpty {
        lines.append("Action: \(action.description)")
      }
      for section in draft.sections where !section.heading.isEmpty || !section.bodyMarkdown.isEmpty {
        lines.append("\(section.heading): \(section.bodyMarkdown)")
      }
      return lines
    }.filter { !$0.isEmpty }

    if let windowTokens, !notes.isEmpty {
      let wrapper = estimatedTokens(reduceInstruction)
      let budget = max(windowTokens - wrapper - completionReserve(windowTokens: windowTokens), 64)
      let share = max(budget / notes.count, 32)
      notes = notes.map { lines in
        var kept: [String] = []
        var used = 0
        for line in lines {
          let cost = estimatedTokens(line) + 1
          if used + cost > share {
            // Keep a truncated head of the first line that does not fit, so a
            // partial never vanishes entirely, then stop.
            if kept.isEmpty {
              kept.append(String(decoding: line.utf8.prefix(max(share * 3 - 3, 64)), as: UTF8.self))
            }
            break
          }
          kept.append(line)
          used += cost
        }
        return kept
      }
    }

    let body = notes.map { $0.joined(separator: "\n") }.joined(separator: "\n\n")
    return """
      \(reduceInstruction)

      \(body)
      """
  }

  private static let reduceInstruction =
    "Write one summary of the conversation described in these notes. Title it after what the conversation was about, never after this instruction. Do not invent facts."
}
