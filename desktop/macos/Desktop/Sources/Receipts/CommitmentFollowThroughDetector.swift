import Foundation

/// Scans new conversation transcripts for evidence that prior pending
/// commitments were fulfilled. Uses Gemini to match commitment text against
/// conversation content and extract proof snippets.
actor CommitmentFollowThroughDetector {
  static let shared = CommitmentFollowThroughDetector()

  private let systemPrompt = """
  You are a commitment follow-through detector. Given a list of pending \
  commitments and a conversation transcript, determine which commitments \
  were fulfilled based on evidence in the conversation.

  A commitment is "fulfilled" if the conversation shows the person did what \
  they promised. Examples:
  - Commitment: "I'll send the report by Friday" → Fulfilled if transcript says "I sent the report" or "the report was sent"
  - Commitment: "I'll review the PR" → Fulfilled if transcript says "I reviewed it" or "the review is done"
  - Commitment: "I'll call them tomorrow" → Fulfilled if transcript says "I called them" or "we spoke on the phone"

  Be conservative: only mark as fulfilled if there is clear evidence. \
  Capture the exact sentence from the transcript as evidence.
  """

  private init() {}

  // MARK: - Public

  /// Check a conversation transcript for evidence that pending commitments
  /// were fulfilled.
  /// - Parameters:
  ///   - commitments: Pending commitments to check
  ///   - transcript: New conversation transcript
  ///   - sessionId: Session ID of the new conversation (for tracking)
  /// - Returns: Results indicating which commitments were fulfilled
  func detect(
    commitments: [CommitmentRecord],
    transcript: [(speaker: String, text: String)],
    sessionId: Int64?
  ) async -> [CommitmentFollowThroughResult] {
    guard !commitments.isEmpty, !transcript.isEmpty else { return [] }

    let prompt = buildPrompt(commitments: commitments, transcript: transcript)

    do {
      let gemini = try GeminiClient()
      let responseText = try await gemini.sendRequest(
        prompt: prompt,
        systemPrompt: systemPrompt,
        responseSchema: responseSchema
      )
      let result = try JSONDecoder().decode(
        FollowThroughBatchResult.self,
        from: Data(responseText.utf8)
      )
      return result.results.filter { $0.fulfilled }
    } catch {
      log("CommitmentFollowThroughDetector: Detection failed: \(error.localizedDescription)")
      return []
    }
  }

  // MARK: - Private

  private func buildPrompt(
    commitments: [CommitmentRecord],
    transcript: [(speaker: String, text: String)]
  ) -> String {
    var lines: [String] = []
    lines.append("PENDING COMMITMENTS:")
    for (i, c) in commitments.enumerated() {
      var entry = "\(i + 1). [ID: \(c.id ?? 0)] \(c.text)"
      if let speaker = c.speaker { entry += " (by: \(speaker))" }
      if let deadline = c.deadline {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        entry += " (deadline: \(formatter.string(from: deadline)))"
      }
      lines.append(entry)
    }
    lines.append("")
    lines.append("CONVERSATION TRANSCRIPT:")
    for segment in transcript {
      lines.append("\(segment.speaker): \(segment.text)")
    }
    lines.append("")
    lines.append("Check each commitment against the transcript. Mark fulfilled=true only with clear evidence.")
    return lines.joined(separator: "\n")
  }

  private var responseSchema: GeminiRequest.GenerationConfig.ResponseSchema {
    let resultProperties: [String: GeminiRequest.GenerationConfig.ResponseSchema.Property] = [
      "commitment_id": .init(
        type: "integer",
        description: "The commitment ID from the pending list"
      ),
      "fulfilled": .init(
        type: "boolean",
        description: "True if the commitment was fulfilled based on transcript evidence"
      ),
      "evidence": .init(
        type: "string",
        description: "The exact sentence from the transcript that proves fulfillment"
      ),
      "confidence": .init(
        type: "number",
        description: "Confidence score 0.0-1.0"
      )
    ]

    return GeminiRequest.GenerationConfig.ResponseSchema(
      type: "object",
      properties: [
        "results": .init(
          type: "array",
          description: "Results for each commitment checked",
          items: .init(
            type: "object",
            properties: resultProperties,
            required: ["commitment_id", "fulfilled", "evidence", "confidence"]
          )
        )
      ],
      required: ["results"]
    )
  }
}
