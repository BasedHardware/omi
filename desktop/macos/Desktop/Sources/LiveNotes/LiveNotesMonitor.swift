import Foundation
import Combine
import GRDB

protocol LiveNoteGenerating {
    func generateNote(prompt: String, systemPrompt: String) async throws -> String
}

extension GeminiClient: LiveNoteGenerating {
    func generateNote(prompt: String, systemPrompt: String) async throws -> String {
        try await sendTextRequest(prompt: prompt, systemPrompt: systemPrompt)
    }
}

protocol LiveNoteStoring {
    func createNote(
        sessionId: Int64,
        text: String,
        timestamp: Date,
        isAiGenerated: Bool,
        segmentStartOrder: Int?,
        segmentEndOrder: Int?
    ) async throws -> LiveNoteRecord
    func updateNote(id: Int64, text: String) async throws
    func deleteNote(id: Int64) async throws
    func getLiveNotes(sessionId: Int64) async throws -> [LiveNote]
}

extension NoteStorage: LiveNoteStoring {}

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

    /// Pure transcript/note policy state for deciding when AI generation should run.
    private var accumulator = LiveNotesAccumulator()

    /// AI note generator (lazily initialized)
    private var noteGenerator: LiveNoteGenerating?

    private let noteGeneratorFactory: () throws -> LiveNoteGenerating

    private let noteStorage: LiveNoteStoring

    /// Cancellables for subscriptions
    private var cancellables = Set<AnyCancellable>()

    /// AI prompt for note generation
    private let noteGenerationPrompt = """
        generate a single, concise note about what happened in this segment.
        be factual and specific.
        focus on the key point or action item.
        keep it a few word sentence.
        do not use quotes.
        do not use wrapping words like "discussion on", jump straight into note.
        avoid repeating information from existing notes.
        """

    private convenience init() {
        self.init(
            noteGeneratorFactory: { try GeminiClient() },
            noteStorage: NoteStorage.shared,
            subscribeToTranscript: true
        )
    }

    init(
        noteGeneratorFactory: @escaping () throws -> LiveNoteGenerating,
        noteStorage: LiveNoteStoring,
        subscribeToTranscript: Bool = false
    ) {
        self.noteGeneratorFactory = noteGeneratorFactory
        self.noteStorage = noteStorage

        if subscribeToTranscript {
            // Subscribe to transcript changes
            LiveTranscriptMonitor.shared.$segments
                .receive(on: DispatchQueue.main)
                .sink { [weak self] segments in
                    self?.handleSegmentsUpdate(segments)
                }
                .store(in: &cancellables)
        }
    }

    // MARK: - Session Lifecycle

    /// Start a new notes session
    func startSession(sessionId: Int64) {
        log("LiveNotesMonitor: Starting session \(sessionId)")
        currentSessionId = sessionId
        notes = []
        isGenerating = false
        accumulator.reset()

        // Initialize AI generator if not already done
        if noteGenerator == nil {
            do {
                // Use Gemini Flash for note generation (text-only, no tool loop — Flash-safe)
                noteGenerator = try noteGeneratorFactory()
                log("LiveNotesMonitor: GeminiClient initialized with default model (Flash)")
            } catch {
                logError("LiveNotesMonitor: Failed to initialize GeminiClient", error: error)
            }
        }

        // Load any existing notes from DB (for crash recovery)
        Task {
            await loadExistingNotes(for: sessionId)
        }
    }

    /// End the current notes session
    func endSession() {
        log("LiveNotesMonitor: Ending session \(currentSessionId ?? -1) with \(notes.count) notes")
        currentSessionId = nil
        isGenerating = false
        accumulator.reset()
    }

    /// Clear all notes (used when recording stops)
    func clear() {
        notes = []
        isGenerating = false
        accumulator.reset()
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
                let record = try await noteStorage.createNote(
                    sessionId: sessionId,
                    text: text,
                    timestamp: Date(),
                    isAiGenerated: false,
                    segmentStartOrder: accumulator.currentSegmentOrder,
                    segmentEndOrder: nil
                )

                if let note = record.toLiveNote() {
                    await MainActor.run {
                        guard self.currentSessionId == sessionId else { return }
                        self.notes.append(note)
                        self.accumulator.appendExistingNote(text)
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
                try await noteStorage.updateNote(id: id, text: text)

                await MainActor.run {
                    if let index = self.notes.firstIndex(where: { $0.id == id }) {
                        var updatedNote = self.notes[index]
                        updatedNote.text = text
                        updatedNote.updatedAt = Date()
                        self.notes[index] = updatedNote
                        self.accumulator.seedExistingNotes(self.notes.map { $0.text })
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
                try await noteStorage.deleteNote(id: id)

                await MainActor.run {
                    if let index = self.notes.firstIndex(where: { $0.id == id }) {
                        self.notes.remove(at: index)
                        self.accumulator.seedExistingNotes(self.notes.map { $0.text })
                    }
                }
            } catch {
                logError("LiveNotesMonitor: Failed to delete note", error: error)
            }
        }
    }

    // MARK: - Private Methods

    /// Load existing notes from DB (for crash recovery)
    private func loadExistingNotes(for sessionId: Int64) async {
        do {
            let existingNotes = try await noteStorage.getLiveNotes(sessionId: sessionId)
            await MainActor.run {
                guard self.currentSessionId == sessionId else { return }
                self.notes = existingNotes
                self.accumulator.seedExistingNotes(existingNotes.map { $0.text })
            }
            log("LiveNotesMonitor: Loaded \(existingNotes.count) existing notes from DB")
        } catch {
            logError("LiveNotesMonitor: Failed to load existing notes", error: error)
        }
    }

    /// Handle transcript segments update
    func handleSegmentsUpdate(_ segments: [SpeakerSegment]) {
        guard currentSessionId != nil, isAiEnabled else { return }

        if let request = accumulator.handleSegmentsUpdate(segments, isGenerating: isGenerating) {
            generateNote(for: request)
        }
    }

    /// Generate an AI note from recent transcript
    private func generateNote(for request: LiveNotesGenerationRequest) {
        guard let sessionId = currentSessionId,
              let generator = noteGenerator,
              !isGenerating else { return }

        isGenerating = true

        let prompt = """
            Transcript segment:
            \(request.recentText)

            \(request.existingNotesText)

            \(noteGenerationPrompt)
            """

        Task {
            do {
                let response = try await generator.generateNote(
                    prompt: prompt,
                    systemPrompt: "You are a concise note-taker. Generate a single short note (3-10 words) about the key point in the transcript. Do not use quotes. Be direct and specific."
                )

                // Clean up the response
                let noteText = response
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                    .replacingOccurrences(of: "\"", with: "")
                    .replacingOccurrences(of: "'", with: "")

                guard !noteText.isEmpty else {
                    await MainActor.run { self.finishGeneration(for: sessionId) }
                    return
                }

                // Save to DB
                let record = try await noteStorage.createNote(
                    sessionId: sessionId,
                    text: noteText,
                    timestamp: Date(),
                    isAiGenerated: true,
                    segmentStartOrder: request.segmentStartOrder,
                    segmentEndOrder: request.segmentEndOrder
                )

                if let note = record.toLiveNote() {
                    await MainActor.run {
                        guard self.currentSessionId == sessionId else { return }
                        self.notes.append(note)
                        self.accumulator.markGenerationSucceeded(noteText: noteText)
                        self.isGenerating = false
                    }
                } else {
                    await MainActor.run { self.finishGeneration(for: sessionId) }
                }
            } catch let dbError as DatabaseError where dbError.resultCode == .SQLITE_CONSTRAINT {
                // Session was deleted during async AI generation — not an error
                log("LiveNotesMonitor: Session \(sessionId) deleted during note generation, skipping")
                await MainActor.run { self.finishGeneration(for: sessionId) }
            } catch {
                logError("LiveNotesMonitor: Failed to generate note", error: error)
                await MainActor.run { self.finishGeneration(for: sessionId) }
            }
        }
    }

    private func finishGeneration(for sessionId: Int64) {
        guard currentSessionId == sessionId else { return }
        isGenerating = false
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
    var wordBufferCount: Int { accumulator.wordBuffer.count }

    /// Existing notes context size (for memory diagnostics)
    var existingNotesContextCount: Int { accumulator.existingNotesContext.count }
}
