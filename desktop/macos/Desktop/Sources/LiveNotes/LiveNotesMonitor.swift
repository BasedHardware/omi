import Combine
import Foundation
@preconcurrency import GRDB

protocol LiveNoteGenerating: Sendable {
  func generateNote(prompt: String, systemPrompt: String) async throws -> String
}

extension GeminiClient: LiveNoteGenerating {
  func generateNote(prompt: String, systemPrompt: String) async throws -> String {
    try await sendTextRequest(prompt: prompt, systemPrompt: systemPrompt)
  }
}

protocol LiveNoteStoring: Sendable {
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

  /// Sync peek used before each generation. BYOK is already folded into
  /// `cachedDecisionForManagedProactivity()` (allow) so this is the only gate.
  private let entitlementDecision: () -> SubscriptionEntitlementDecision

  /// Optional cache refresh so a mid-session upgrade/BYOK change can unlatch
  /// without an app restart. Tests leave this nil.
  private let refreshEntitlement: (@Sendable () async -> Void)?

  private let logGenerationFailure: (String, Error) -> Void

  /// Server 402 `plan_gated` latch. Survives fail-open cached `.allow` until the
  /// entitlement decision actually changes, or until `serverDenialLifetime`
  /// passes: when the cached plan was unknown (fail-open allow) an upgrade leaves
  /// the decision at allow, so nothing else would ever clear the latch. One
  /// probe per lifetime is the cost of noticing that upgrade without a restart.
  private var serverDeniedManagedNotes = false
  private var serverDeniedAt: Date?
  static let serverDenialLifetime: TimeInterval = 10 * 60

  private var lastEntitlementDecision: SubscriptionEntitlementDecision?

  private var didLogPlanGateSkip = false

  private var entitlementRefreshInFlight = false

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
      noteGeneratorFactory: { try GeminiClient(model: ModelQoS.Gemini.lightweight, workload: .extraction) },
      noteStorage: NoteStorage.shared,
      subscribeToTranscript: true,
      entitlementDecision: {
        SubscriptionEntitlementService.shared.cachedDecisionForManagedProactivity()
      },
      refreshEntitlement: {
        _ = await SubscriptionEntitlementService.shared.snapshot()
      }
    )
  }

  init(
    noteGeneratorFactory: @escaping () throws -> LiveNoteGenerating,
    noteStorage: LiveNoteStoring,
    subscribeToTranscript: Bool = false,
    entitlementDecision: @escaping () -> SubscriptionEntitlementDecision = {
      SubscriptionEntitlementService.shared.cachedDecisionForManagedProactivity()
    },
    refreshEntitlement: (@Sendable () async -> Void)? = nil,
    logGenerationFailure: @escaping (String, Error) -> Void = { message, error in
      logError(message, error: error)
    }
  ) {
    self.noteGeneratorFactory = noteGeneratorFactory
    self.noteStorage = noteStorage
    self.entitlementDecision = entitlementDecision
    self.refreshEntitlement = refreshEntitlement
    self.logGenerationFailure = logGenerationFailure

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
    guard currentSessionId != nil, !isGenerating else { return }
    if shouldSkipManagedAINotes() { return }

    guard let sessionId = currentSessionId,
      let generator = noteGenerator
    else { return }

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
          systemPrompt:
            "You are a concise note-taker. Generate a single short note (3-10 words) about the key point in the transcript. Do not use quotes. Be direct and specific."
        )

        // Clean up the response
        let noteText =
          response
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
        if Self.isPlanGatedGenerationError(error) {
          await MainActor.run {
            self.latchPlanGateFromServer()
            self.finishGeneration(for: sessionId)
          }
        } else {
          self.logGenerationFailure("LiveNotesMonitor: Failed to generate note", error)
          await MainActor.run { self.finishGeneration(for: sessionId) }
        }
      }
    }
  }

  private func finishGeneration(for sessionId: Int64) {
    guard currentSessionId == sessionId else { return }
    isGenerating = false
  }

  /// Skip managed AI notes when the cached decision is `.planGated` (BYOK already
  /// maps to `.allowManagedProactivity`) or after a typed server `plan_gated`.
  /// A later decision change to allow unlatches so an upgrade resumes notes.
  private func shouldSkipManagedAINotes() -> Bool {
    let decision = entitlementDecision()
    if lastEntitlementDecision != decision {
      lastEntitlementDecision = decision
      if decision == .allowManagedProactivity {
        serverDeniedManagedNotes = false
        serverDeniedAt = nil
        didLogPlanGateSkip = false
      }
    }

    if serverDeniedManagedNotes, let deniedAt = serverDeniedAt,
      Date().timeIntervalSince(deniedAt) >= Self.serverDenialLifetime
    {
      serverDeniedManagedNotes = false
      serverDeniedAt = nil
      didLogPlanGateSkip = false
    }

    if decision == .planGated || serverDeniedManagedNotes {
      logPlanGateSkipOnce()
      requestEntitlementRefresh()
      return true
    }
    return false
  }

  private func latchPlanGateFromServer() {
    serverDeniedManagedNotes = true
    serverDeniedAt = Date()
    logPlanGateSkipOnce()
    requestEntitlementRefresh()
  }

  private func logPlanGateSkipOnce() {
    guard !didLogPlanGateSkip else { return }
    didLogPlanGateSkip = true
    log("LiveNotesMonitor: AI notes unavailable on this plan; skipping generation")
  }

  private func requestEntitlementRefresh() {
    guard let refreshEntitlement, !entitlementRefreshInFlight else { return }
    entitlementRefreshInFlight = true
    Task { [weak self] in
      await refreshEntitlement()
      await MainActor.run {
        self?.entitlementRefreshInFlight = false
      }
    }
  }

  private static func isPlanGatedGenerationError(_ error: Error) -> Bool {
    if case GeminiClient.GeminiClientError.planGated = error {
      return true
    }
    if case ProactiveLaneClientError.planGated = error {
      return true
    }
    return false
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
