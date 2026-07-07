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

    private var lastProcessedSegmentEnd: Double?
    private var wordsSinceLastGeneration = 0

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
        lastProcessedSegmentEnd = nil
        wordsSinceLastGeneration = 0
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

        let newSegments: ArraySlice<SpeakerSegment>
        if let lastProcessedSegmentEnd {
            guard let startIndex = segments.firstIndex(where: { $0.end > lastProcessedSegmentEnd }) else {
                return nil
            }
            newSegments = segments[startIndex...]
        } else {
            newSegments = segments[...]
        }

        let newWords = newSegments.flatMap { segment in
            segment.text.split(separator: " ").map(String.init)
        }
        guard !newWords.isEmpty else { return nil }

        if let lastSegment = segments.last {
            lastProcessedSegmentEnd = lastSegment.end
        }

        wordBuffer.append(contentsOf: newWords)
        wordsSinceLastGeneration += newWords.count
        trimWordBuffer()

        guard wordsSinceLastGeneration >= wordThreshold, !isGenerating else {
            return nil
        }

        return LiveNotesGenerationRequest(
            recentText: wordBuffer.suffix(wordThreshold).joined(separator: " "),
            existingNotesText: existingNotesText(),
            segmentStartOrder: max(0, currentSegmentOrder - 3),
            segmentEndOrder: currentSegmentOrder
        )
    }

    mutating func markGenerationSucceeded(noteText: String) {
        wordsSinceLastGeneration = 0
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
