import Foundation
import Combine
import GRDB

/// Dedicated monitor for live notes generation during recording sessions.
/// Accumulates transcript words and triggers AI note generation at word thresholds.
/// Only views that explicitly observe this class will update when notes change.
@MainActor
class LiveNotesMonitor: ObservableObject {
    static let shared = LiveNotesMonitor()

    /// Live notes for real-time display
    @Published private(set) var notes: [LiveNote] = []

    /// Whether AI note generation is enabled
    @Published var isAiEnabled: Bool = true

    /// Whether a note is currently being generated
    @Published private(set) var isGenerating: Bool = false

    /// Current recording session ID
    private var currentSessionId: Int64?

    /// Word buffer for tracking transcript content
    private var wordBuffer: [String] = []

    /// Segment order tracking for note context
    private var lastProcessedSegmentOrder: Int = -1

    /// Current segment order being processed
    private var currentSegmentOrder: Int = 0

    /// End time of the last segment we extracted words from (cursor for incremental processing)
    private var lastProcessedSegmentEnd: Double?

    /// Minimum words before triggering AI generation
    private let wordThreshold = 50

    /// Max words to keep in buffer (older words are trimmed)
    private let maxWordBufferSize = 500

    /// Max existing notes to keep for context (oldest trimmed)
    private let maxExistingNotesContext = 20

    /// Existing notes for context (to avoid repetition)
    private var existingNotesContext: [String] = []

    /// GeminiClient for AI generation (lazily initialized)
    private var geminiClient: GeminiClient?

    /// Cancellables for subscriptions
    private var cancellables = Set<AnyCancellable>()

    /// AI prompt for note generation (from m13v/meeting)
    private let noteGenerationPrompt = """
        generate a single, concise note about what happened in this segment.
        be factual and specific.
        focus on the key point or action item.
        keep it a few word sentence.
        do not use quotes.
        do not use wrapping words like "discussion on", jump straight into note.
        avoid repeating information from existing notes.
        """

    private init() {
        // Subscribe to transcript changes
        LiveTranscriptMonitor.shared.$segments
            .receive(on: DispatchQueue.main)
            .sink { [weak self] segments in
                self?.handleSegmentsUpdate(segments)
            }
            .store(in: &cancellables)
    }

    // MARK: - Session Lifecycle

    /// Start a new notes session
    func startSession(sessionId: Int64) {
        log("LiveNotesMonitor: Starting session \(sessionId)")
        currentSessionId = sessionId
        notes = []
        wordBuffer = []
        lastProcessedSegmentOrder = -1
        currentSegmentOrder = 0
        lastProcessedSegmentEnd = nil
        existingNotesContext = []

        // Initialize Gemini client if not already done
        if geminiClient == nil {
            do {
                // Use Gemini 3 Pro for better note generation quality
                geminiClient = try GeminiClient(model: "gemini-pro-latest")
                log("LiveNotesMonitor: GeminiClient initialized with gemini-pro-latest")
            } catch {
                logError("LiveNotesMonitor: Failed to initialize GeminiClient", error: error)
            }
        }

        // Load any existing notes from DB (for crash recovery)
        Task {
            await loadExistingNotes()
        }
    }

    /// End the current notes session
    func endSession() {
        log("LiveNotesMonitor: Ending session \(currentSessionId ?? -1) with \(notes.count) notes")
        currentSessionId = nil
        wordBuffer = []
        lastProcessedSegmentOrder = -1
        currentSegmentOrder = 0
        lastProcessedSegmentEnd = nil
    }

    /// Clear all notes (used when recording stops)
    func clear() {
        notes = []
        wordBuffer = []
        existingNotesContext = []
        lastProcessedSegmentOrder = -1
        currentSegmentOrder = 0
        lastProcessedSegmentEnd = nil
    }

    // MARK: - Note Operations

    /// Add a manual note
    func addManualNote(text: String) {
        guard let sessionId = currentSessionId else {
            log("LiveNotesMonitor: Cannot add note - no active session")
            return
        }

        Task {
            do {
                let record = try await NoteStorage.shared.createNote(
                    sessionId: sessionId,
                    text: text,
                    isAiGenerated: false,
                    segmentStartOrder: currentSegmentOrder
                )

                if let note = record.toLiveNote() {
                    await MainActor.run {
                        self.notes.append(note)
                        self.existingNotesContext.append(text)
                        // Trim context to prevent unbounded growth
                        if self.existingNotesContext.count > self.maxExistingNotesContext {
                            self.existingNotesContext.removeFirst(self.existingNotesContext.count - self.maxExistingNotesContext)
                        }
                    }
                }
            } catch {
                logError("LiveNotesMonitor: Failed to add manual note", error: error)
            }
        }
    }

    /// Update an existing note
    func updateNote(id: Int64, text: String) {
        Task {
            do {
                try await NoteStorage.shared.updateNote(id: id, text: text)

                await MainActor.run {
                    if let index = self.notes.firstIndex(where: { $0.id == id }) {
                        var updatedNote = self.notes[index]
                        updatedNote.text = text
                        updatedNote.updatedAt = Date()
                        self.notes[index] = updatedNote
                    }
                }
            } catch {
                logError("LiveNotesMonitor: Failed to update note", error: error)
            }
        }
    }

    /// Delete a note
    func deleteNote(id: Int64) {
        Task {
            do {
                try await NoteStorage.shared.deleteNote(id: id)

                await MainActor.run {
                    self.notes.removeAll { $0.id == id }
                }
            } catch {
                logError("LiveNotesMonitor: Failed to delete note", error: error)
            }
        }
    }

    // MARK: - Private Methods

    /// Load existing notes from DB (for crash recovery)
    private func loadExistingNotes() async {
        guard let sessionId = currentSessionId else { return }

        do {
            let existingNotes = try await NoteStorage.shared.getLiveNotes(sessionId: sessionId)
            await MainActor.run {
                self.notes = existingNotes
                self.existingNotesContext = existingNotes.map { $0.text }
            }
            log("LiveNotesMonitor: Loaded \(existingNotes.count) existing notes from DB")
        } catch {
            logError("LiveNotesMonitor: Failed to load existing notes", error: error)
        }
    }

    /// Handle transcript segments update
    private func handleSegmentsUpdate(_ segments: [SpeakerSegment]) {
        guard currentSessionId != nil, isAiEnabled else { return }

        // Track segment order
        currentSegmentOrder = segments.count

        // Only extract words from segments we haven't processed yet.
        // Use the last processed segment's end time as a cursor to find new content.
        let newSegments: ArraySlice<SpeakerSegment>
        if let lastEnd = lastProcessedSegmentEnd {
            // Find segments that are new or were updated (end time > last processed)
            if let startIdx = segments.firstIndex(where: { $0.end > lastEnd }) {
                newSegments = segments[startIdx...]
            } else {
                return  // No new segments
            }
        } else {
            newSegments = segments[...]
        }

        let newWords = newSegments.flatMap { $0.text.split(separator: " ").map(String.init) }
        guard !newWords.isEmpty else { return }

        // Update cursor to the end of the last segment we processed
        if let lastSeg = segments.last {
            lastProcessedSegmentEnd = lastSeg.end
        }

        wordBuffer.append(contentsOf: newWords)

        // Trim word buffer to prevent unbounded growth (keep most recent words)
        if wordBuffer.count > maxWordBufferSize {
            wordBuffer.removeFirst(wordBuffer.count - maxWordBufferSize)
        }

        // Check if we have enough words to generate a note
        let wordsSinceLastNote = wordBuffer.count - (lastProcessedSegmentOrder >= 0 ? lastProcessedSegmentOrder : 0)
        if wordsSinceLastNote >= wordThreshold && !isGenerating {
            generateNote(from: segments)
        }
    }

    /// Generate an AI note from recent transcript
    private func generateNote(from segments: [SpeakerSegment]) {
        guard let sessionId = currentSessionId,
              let client = geminiClient,
              !isGenerating else { return }

        isGenerating = true

        // Get recent transcript text (last ~50 words)
        let recentText = wordBuffer.suffix(wordThreshold).joined(separator: " ")
        let segmentStartOrder = max(0, currentSegmentOrder - 3)
        let segmentEndOrder = currentSegmentOrder

        // Build context from existing notes
        let existingNotesText = existingNotesContext.isEmpty
            ? "No existing notes yet."
            : "Existing notes:\n" + existingNotesContext.map { "- \($0)" }.joined(separator: "\n")

        let prompt = """
            Transcript segment:
            \(recentText)

            \(existingNotesText)

            \(noteGenerationPrompt)
            """

        Task {
            do {
                let response = try await client.sendTextRequest(
                    prompt: prompt,
                    systemPrompt: "You are a concise note-taker. Generate a single short note (3-10 words) about the key point in the transcript. Do not use quotes. Be direct and specific."
                )

                // Clean up the response
                let noteText = response
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                    .replacingOccurrences(of: "\"", with: "")
                    .replacingOccurrences(of: "'", with: "")

                guard !noteText.isEmpty else {
                    await MainActor.run { self.isGenerating = false }
                    return
                }

                // Save to DB
                let record = try await NoteStorage.shared.createNote(
                    sessionId: sessionId,
                    text: noteText,
                    isAiGenerated: true,
                    segmentStartOrder: segmentStartOrder,
                    segmentEndOrder: segmentEndOrder
                )

                if let note = record.toLiveNote() {
                    await MainActor.run {
                        self.notes.append(note)
                        self.existingNotesContext.append(noteText)
                        // Trim context to prevent unbounded growth (keep most recent notes)
                        if self.existingNotesContext.count > self.maxExistingNotesContext {
                            self.existingNotesContext.removeFirst(self.existingNotesContext.count - self.maxExistingNotesContext)
                        }
                        self.lastProcessedSegmentOrder = self.wordBuffer.count
                        self.isGenerating = false
                    }
                } else {
                    await MainActor.run { self.isGenerating = false }
                }
            } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
                // Session was deleted during async AI generation — not an error
                log("LiveNotesMonitor: Session \(sessionId) deleted during note generation, skipping")
                await MainActor.run { self.isGenerating = false }
            } catch {
                logError("LiveNotesMonitor: Failed to generate note", error: error)
                await MainActor.run { self.isGenerating = false }
            }
        }
    }

    // MARK: - Computed Properties

    /// Check if there are any notes
    var isEmpty: Bool {
        notes.isEmpty
    }

    /// Get the latest note
    var latestNote: LiveNote? {
        notes.last
    }

    /// Get notes for current session
    func getNotesForCurrentSession() -> [LiveNote] {
        return notes
    }

    // MARK: - Diagnostics

    /// Word buffer size (for memory diagnostics)
    var wordBufferCount: Int { wordBuffer.count }

    /// Existing notes context size (for memory diagnostics)
    var existingNotesContextCount: Int { existingNotesContext.count }
}
