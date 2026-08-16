import Foundation

struct LiveNotesGenerationRequest: Equatable {
  let recentText: String
  let existingNotesText: String
  let segmentStartOrder: Int
  let segmentEndOrder: Int
}

struct LiveNotesAccumulator {
  let wordThreshold: Int
  let maxWordBufferSize: Int
  let maxExistingNotesContext: Int

  private(set) var wordBuffer: [String] = []
  private(set) var existingNotesContext: [String] = []
  private(set) var currentSegmentOrder: Int = 0

  private var processedSegmentWordCounts: [String: Int] = [:]
  private var wordsSinceLastGeneration = 0
  /// Number of words included in the most recent generation request's window.
  /// `markGenerationSucceeded` decrements the unsummarized counter by exactly
  /// this, so words that arrived while the generation was in flight are kept.
  private var wordsInFlightForGeneration = 0

  init(
    wordThreshold: Int = 50,
    maxWordBufferSize: Int = 500,
    maxExistingNotesContext: Int = 20
  ) {
    self.wordThreshold = wordThreshold
    self.maxWordBufferSize = maxWordBufferSize
    self.maxExistingNotesContext = maxExistingNotesContext
  }

  mutating func reset() {
    wordBuffer = []
    existingNotesContext = []
    currentSegmentOrder = 0
    processedSegmentWordCounts = [:]
    wordsSinceLastGeneration = 0
    wordsInFlightForGeneration = 0
  }

  mutating func seedExistingNotes(_ notes: [String]) {
    existingNotesContext = trimmedContext(notes)
  }

  mutating func appendExistingNote(_ note: String) {
    existingNotesContext.append(note)
    trimExistingNotesContext()
  }

  mutating func handleSegmentsUpdate(
    _ segments: [SpeakerSegment],
    isGenerating: Bool
  ) -> LiveNotesGenerationRequest? {
    currentSegmentOrder = segments.count

    let currentSegmentIds = Set(segments.map(\.id))
    processedSegmentWordCounts = processedSegmentWordCounts.filter { currentSegmentIds.contains($0.key) }

    let newWords = segments.flatMap { segment in
      let words = segment.text.split(separator: " ").map(String.init)
      let processedCount = processedSegmentWordCounts[segment.id] ?? 0
      processedSegmentWordCounts[segment.id] = words.count

      guard words.count > processedCount else { return [String]() }
      return Array(words.dropFirst(processedCount))
    }
    guard !newWords.isEmpty else { return nil }

    wordBuffer.append(contentsOf: newWords)
    wordsSinceLastGeneration += newWords.count
    trimWordBuffer()
    // A word can't be "unsummarized" if it was already trimmed out of the
    // buffer, so cap the counter at the buffered word count. Without this, an
    // extreme burst larger than the buffer would leave a residual counter that
    // re-summarizes the same tail forever.
    wordsSinceLastGeneration = min(wordsSinceLastGeneration, wordBuffer.count)

    guard wordsSinceLastGeneration >= wordThreshold, !isGenerating else {
      return nil
    }

    // Summarize ALL unsummarized words, not just the last `wordThreshold`. When
    // a single update (or accumulation while a prior generation was in flight)
    // brings more than `wordThreshold` new words, a fixed suffix(wordThreshold)
    // window dropped the middle span and re-summarized the tail.
    let generationWindow = wordsSinceLastGeneration
    wordsInFlightForGeneration = generationWindow

    return LiveNotesGenerationRequest(
      recentText: wordBuffer.suffix(generationWindow).joined(separator: " "),
      existingNotesText: existingNotesText(),
      segmentStartOrder: max(0, currentSegmentOrder - 3),
      segmentEndOrder: currentSegmentOrder
    )
  }

  mutating func markGenerationSucceeded(noteText: String) {
    // Decrement only by the window that was actually summarized, so words that
    // arrived while this generation was in flight remain unsummarized.
    wordsSinceLastGeneration = max(0, wordsSinceLastGeneration - wordsInFlightForGeneration)
    wordsInFlightForGeneration = 0
    appendExistingNote(noteText)
  }

  private mutating func trimWordBuffer() {
    guard wordBuffer.count > maxWordBufferSize else { return }
    wordBuffer.removeFirst(wordBuffer.count - maxWordBufferSize)
  }

  private mutating func trimExistingNotesContext() {
    existingNotesContext = trimmedContext(existingNotesContext)
  }

  private func trimmedContext(_ notes: [String]) -> [String] {
    guard notes.count > maxExistingNotesContext else { return notes }
    return Array(notes.suffix(maxExistingNotesContext))
  }

  private func existingNotesText() -> String {
    if existingNotesContext.isEmpty {
      return "No existing notes yet."
    }

    return "Existing notes:\n" + existingNotesContext.map { "- \($0)" }.joined(separator: "\n")
  }
}
