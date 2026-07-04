import Foundation

/// Extracts commitments from conversation transcripts using Gemini.
/// A "commitment" is a promise or obligation the user (or someone in the
/// conversation) made — e.g. "I'll send the report by Friday".
actor CommitmentExtractor {
  static let shared = CommitmentExtractor()

  private let systemPrompt = """
  You are a commitment detection assistant. Analyze conversation transcripts \
  and extract explicit commitments, promises, and obligations made by any \
  speaker. A commitment is something someone agreed to do, promised to \
  deliver, or committed to follow up on.

  Extract ONLY explicit commitments — not vague intentions or passing remarks.
  Examples of commitments:
  - "I'll send the report by Friday"
  - "Let me check and get back to you"
  - "I'll review the PR today"
  - "We'll ship this by end of week"
  - "I promise to call them tomorrow"

  Do NOT extract:
  - Questions ("can you send it?")
  - Vague wishes ("it would be nice to...")
  - Past completed actions ("I sent it yesterday")
  - General observations

  If a deadline is mentioned or implied, capture it as an ISO 8601 datetime. \
  If no deadline is mentioned, leave deadline_iso null.
  """

  private init() {}

  // MARK: - Public

  /// Extract commitments from a conversation transcript.
  /// - Parameters:
  ///   - transcript: Array of (speaker, text) tuples representing the conversation
  ///   - conversationDate: When the conversation happened (for relative deadline resolution)
  /// - Returns: Array of extracted commitments, or empty if none found
  func extract(
    from transcript: [(speaker: String, text: String)],
    conversationDate: Date = Date()
  ) async -> [ExtractedCommitment] {
    guard !transcript.isEmpty else { return [] }

    let prompt = buildPrompt(transcript: transcript, conversationDate: conversationDate)

    do {
      let gemini = try GeminiClient()
      let responseText = try await gemini.sendRequest(
        prompt: prompt,
        systemPrompt: systemPrompt,
        responseSchema: responseSchema
      )
      let result = try JSONDecoder().decode(
        CommitmentExtractionResult.self,
        from: Data(responseText.utf8)
      )
      return result.hasCommitments ? result.commitments : []
    } catch {
      log("CommitmentExtractor: Extraction failed: \(error.localizedDescription)")
      return []
    }
  }

  // MARK: - Private

  private func buildPrompt(
    transcript: [(speaker: String, text: String)],
    conversationDate: Date
  ) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    let conversationISO = formatter.string(from: conversationDate)

    var lines: [String] = []
    lines.append("Conversation date (ISO 8601): \(conversationISO)")
    lines.append("Today's date (ISO 8601): \(formatter.string(from: Date()))")
    lines.append("")
    lines.append("TRANSCRIPT:")
    for segment in transcript {
      lines.append("\(segment.speaker): \(segment.text)")
    }
    lines.append("")
    lines.append("Extract all explicit commitments from this transcript.")
    return lines.joined(separator: "\n")
  }

  private var responseSchema: GeminiRequest.GenerationConfig.ResponseSchema {
    let commitmentProperties: [String: GeminiRequest.GenerationConfig.ResponseSchema.Property] = [
      "text": .init(
        type: "string",
        description: "The commitment text — what was promised (max 20 words)"
      ),
      "speaker": .init(
        type: "string",
        description: "Who made the commitment (speaker name or 'user')"
      ),
      "deadline_iso": .init(
        type: "string",
        description: "ISO 8601 datetime if a deadline was mentioned, otherwise null"
      ),
      "confidence": .init(
        type: "number",
        description: "Confidence score 0.0-1.0"
      )
    ]

    return GeminiRequest.GenerationConfig.ResponseSchema(
      type: "object",
      properties: [
        "has_commitments": .init(
          type: "boolean",
          description: "True if any explicit commitments were found"
        ),
        "commitments": .init(
          type: "array",
          description: "Array of extracted commitments (0-10 max)",
          items: .init(
            type: "object",
            properties: commitmentProperties,
            required: ["text", "speaker", "deadline_iso", "confidence"]
          )
        )
      ],
      required: ["has_commitments", "commitments"]
    )
  }
}
