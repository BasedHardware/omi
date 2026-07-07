import GRDB
import XCTest
@testable import Omi_Computer

@MainActor
final class LiveNotesMonitorTests: XCTestCase {
    func testAiGenerationSuccessPersistsAndAppendsNote() async throws {
        let generator = FakeLiveNoteGenerator(results: [.success("\"Project timeline settled\"")])
        let storage = FakeLiveNoteStorage()
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { generator },
            noteStorage: storage
        )
        monitor.startSession(sessionId: 42)
        await waitForSessionLoad(storage)

        monitor.handleSegmentsUpdate([segment(text: words(50), start: 0, end: 1)])

        await waitUntil("AI generation persisted note") {
            monitor.notes.count == 1 && !monitor.isGenerating
        }

        XCTAssertEqual(monitor.notes.map(\.text), ["Project timeline settled"])
        XCTAssertEqual(monitor.notes.first?.sessionId, 42)
        XCTAssertEqual(monitor.notes.first?.isAiGenerated, true)
        XCTAssertEqual(monitor.notes.first?.segmentStartOrder, 0)
        XCTAssertEqual(monitor.notes.first?.segmentEndOrder, 1)

        let created = await storage.createdNotes()
        XCTAssertEqual(created.map(\.text), ["Project timeline settled"])
        XCTAssertEqual(created.first?.isAiGenerated, true)
    }

    func testAiEmptyResponseDoesNotWedgeGeneration() async throws {
        let generator = FakeLiveNoteGenerator(results: [.success(" \n \"' ")])
        let storage = FakeLiveNoteStorage()
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { generator },
            noteStorage: storage
        )
        monitor.startSession(sessionId: 42)
        await waitForSessionLoad(storage)

        monitor.handleSegmentsUpdate([segment(text: words(50), start: 0, end: 1)])

        await waitUntil("empty AI response unwound generation") {
            !monitor.isGenerating
        }

        XCTAssertTrue(monitor.notes.isEmpty)
        let promptCount = await generator.prompts().count
        XCTAssertEqual(promptCount, 1)
        let created = await storage.createdNotes()
        XCTAssertTrue(created.isEmpty)
    }

    func testAiFailureDoesNotWedgeGeneration() async throws {
        let generator = FakeLiveNoteGenerator(results: [.failure(TestError.generationFailed)])
        let storage = FakeLiveNoteStorage()
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { generator },
            noteStorage: storage
        )
        monitor.startSession(sessionId: 42)
        await waitForSessionLoad(storage)

        monitor.handleSegmentsUpdate([segment(text: words(50), start: 0, end: 1)])

        await waitUntil("failed AI response unwound generation") {
            !monitor.isGenerating
        }

        XCTAssertTrue(monitor.notes.isEmpty)
        let promptCount = await generator.prompts().count
        XCTAssertEqual(promptCount, 1)
        let created = await storage.createdNotes()
        XCTAssertTrue(created.isEmpty)
    }

    func testSessionDeletedConstraintDoesNotWedgeGeneration() async throws {
        let generator = FakeLiveNoteGenerator(results: [.success("Follow up with design")])
        let storage = FakeLiveNoteStorage(createError: DatabaseError(resultCode: .SQLITE_CONSTRAINT, message: "session deleted"))
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { generator },
            noteStorage: storage
        )
        monitor.startSession(sessionId: 42)
        await waitForSessionLoad(storage)

        monitor.handleSegmentsUpdate([segment(text: words(50), start: 0, end: 1)])

        await waitUntil("constraint unwound generation") {
            !monitor.isGenerating
        }

        XCTAssertTrue(monitor.notes.isEmpty)
        let promptCount = await generator.prompts().count
        XCTAssertEqual(promptCount, 1)
    }

    func testManualAddUpdateDeleteKeepsNotesAndGenerationContextCoherent() async throws {
        let generator = FakeLiveNoteGenerator(results: [
            .success("AI kept project context"),
            .success("AI continued after cleanup"),
        ])
        let storage = FakeLiveNoteStorage()
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { generator },
            noteStorage: storage
        )
        monitor.startSession(sessionId: 42)
        await waitForSessionLoad(storage)

        monitor.addManualNote(text: "manual alpha")
        await waitUntil("manual note appended") {
            monitor.notes.map(\.text) == ["manual alpha"]
        }

        monitor.handleSegmentsUpdate([segment(text: words(50, prefix: "first"), start: 0, end: 1)])
        await waitUntil("first AI note appended") {
            monitor.notes.map(\.text) == ["manual alpha", "AI kept project context"]
        }

        let firstPrompt = await generator.prompts()[0]
        XCTAssertTrue(firstPrompt.contains("- manual alpha"))

        let manualId = try XCTUnwrap(monitor.notes.first?.id)
        monitor.updateNote(id: manualId, text: "manual beta")
        await waitUntil("manual note updated") {
            monitor.notes.first?.text == "manual beta"
        }

        monitor.deleteNote(id: manualId)
        await waitUntil("manual note deleted") {
            monitor.notes.map(\.text) == ["AI kept project context"]
        }

        monitor.handleSegmentsUpdate([
            segment(text: words(50, prefix: "first"), start: 0, end: 1),
            segment(text: words(50, prefix: "second"), start: 1, end: 2),
        ])
        await waitUntil("second AI note appended") {
            monitor.notes.map(\.text) == ["AI kept project context", "AI continued after cleanup"]
        }

        let secondPrompt = await generator.prompts()[1]
        XCTAssertFalse(secondPrompt.contains("manual alpha"))
        XCTAssertFalse(secondPrompt.contains("manual beta"))
        XCTAssertTrue(secondPrompt.contains("- AI kept project context"))
    }

    func testUpdatingAndDeletingDuplicateNotesRebuildsGenerationContextByIdentity() async throws {
        let generator = FakeLiveNoteGenerator(results: [
            .success("AI after duplicate edit"),
            .success("AI after duplicate delete"),
        ])
        let storage = FakeLiveNoteStorage(
            existingNotes: [
                liveNoteRecord(id: 1, sessionId: 42, text: "duplicate note"),
                liveNoteRecord(id: 2, sessionId: 42, text: "duplicate note"),
            ]
        )
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { generator },
            noteStorage: storage
        )
        monitor.startSession(sessionId: 42)
        await waitUntil("duplicate notes loaded") {
            monitor.notes.map(\.id) == [1, 2]
        }

        monitor.updateNote(id: 2, text: "edited duplicate note")
        await waitUntil("duplicate note updated") {
            monitor.notes.map(\.text) == ["duplicate note", "edited duplicate note"]
        }

        monitor.handleSegmentsUpdate([segment(text: words(50, prefix: "first"), start: 0, end: 1)])
        await waitUntil("first duplicate prompt generated") {
            await generator.prompts().count == 1
        }

        let firstPrompt = await generator.prompts()[0]
        XCTAssertTrue(firstPrompt.contains("Existing notes:\n- duplicate note\n- edited duplicate note"))

        monitor.deleteNote(id: 2)
        await waitUntil("edited duplicate deleted") {
            monitor.notes.map(\.text) == ["duplicate note", "AI after duplicate edit"]
        }

        monitor.handleSegmentsUpdate([
            segment(text: words(50, prefix: "first"), start: 0, end: 1),
            segment(text: words(50, prefix: "second"), start: 1, end: 2),
        ])
        await waitUntil("second duplicate prompt generated") {
            await generator.prompts().count == 2
        }

        let secondPrompt = await generator.prompts()[1]
        XCTAssertTrue(secondPrompt.contains("- duplicate note"))
        XCTAssertTrue(secondPrompt.contains("- AI after duplicate edit"))
        XCTAssertFalse(secondPrompt.contains("edited duplicate note"))
    }

    func testLateSessionLoadCannotOverwriteNewSessionNotes() async throws {
        let storage = FakeLiveNoteStorage(
            existingNotes: [
                liveNoteRecord(id: 11, sessionId: 1, text: "old session note"),
                liveNoteRecord(id: 22, sessionId: 2, text: "current session note"),
            ],
            suspendedLoadSessionId: 1
        )
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { FakeLiveNoteGenerator(results: []) },
            noteStorage: storage
        )

        monitor.startSession(sessionId: 1)
        await waitUntil("first session load suspended") {
            await storage.isLoadSuspended(sessionId: 1)
        }

        monitor.startSession(sessionId: 2)
        await waitUntil("second session notes loaded") {
            monitor.notes.map(\.text) == ["current session note"]
        }

        await storage.resumeLoad(sessionId: 1)
        await waitForAsyncWorkToSettle()

        XCTAssertEqual(monitor.notes.map(\.text), ["current session note"])
        XCTAssertEqual(monitor.notes.map(\.sessionId), [2])
    }

    func testLateAiGenerationCannotAppendToNewSessionOrClearItsGenerationState() async throws {
        let oldGenerator = FakeLiveNoteGenerator(
            results: [.success("late old-session note"), .success("new session note")],
            suspendedResponseLimit: 2
        )
        let storage = FakeLiveNoteStorage()
        let monitor = LiveNotesMonitor(
            noteGeneratorFactory: { oldGenerator },
            noteStorage: storage
        )

        monitor.startSession(sessionId: 1)
        await waitForSessionLoad(storage)
        monitor.handleSegmentsUpdate([segment(text: words(50, prefix: "old"), start: 0, end: 1)])
        await waitUntil("old session generation suspended") {
            await oldGenerator.isResponseSuspended()
        }

        monitor.startSession(sessionId: 2)
        await waitUntil("new session reset generation state") {
            !monitor.isGenerating
        }
        monitor.handleSegmentsUpdate([segment(text: words(50, prefix: "new"), start: 0, end: 1)])
        await waitUntil("new session generation suspended") {
            let suspendedResponses = await oldGenerator.suspendedResponseCount()
            return monitor.isGenerating && suspendedResponses == 2
        }

        await oldGenerator.resumeResponse()
        await waitForAsyncWorkToSettle()

        XCTAssertTrue(monitor.notes.isEmpty)
        XCTAssertTrue(monitor.isGenerating)

        await oldGenerator.resumeResponse()
        await waitUntil("new session note appended") {
            monitor.notes.map(\.text) == ["new session note"] && !monitor.isGenerating
        }

        XCTAssertEqual(monitor.notes.map(\.sessionId), [2])
        let created = await storage.createdNotes()
        XCTAssertEqual(created.map(\.text), ["late old-session note", "new session note"])
    }

    private func waitForSessionLoad(_ storage: FakeLiveNoteStorage) async {
        await waitUntil("session load completed") {
            await storage.getLiveNotesCallCount() > 0
        }
    }

    private func waitUntil(
        _ description: String,
        file: StaticString = #filePath,
        line: UInt = #line,
        condition: () async -> Bool
    ) async {
        for _ in 0..<1_000 {
            if await condition() {
                return
            }
            await Task.yield()
        }
        XCTFail("Timed out waiting for \(description)", file: file, line: line)
    }

    private func waitForAsyncWorkToSettle() async {
        for _ in 0..<10 {
            await Task.yield()
        }
    }

    private func words(_ count: Int, prefix: String = "word") -> String {
        (0..<count).map { "\(prefix)\($0)" }.joined(separator: " ")
    }

    private func segment(text: String, start: Double, end: Double) -> SpeakerSegment {
        SpeakerSegment(
            segmentId: nil,
            speaker: 1,
            text: text,
            start: start,
            end: end
        )
    }

    private func liveNoteRecord(id: Int64, sessionId: Int64, text: String) -> LiveNoteRecord {
        LiveNoteRecord(
            id: id,
            sessionId: sessionId,
            text: text,
            timestamp: Date(),
            isAiGenerated: false,
            segmentStartOrder: nil,
            segmentEndOrder: nil,
            createdAt: Date(),
            updatedAt: Date()
        )
    }
}

private actor FakeLiveNoteGenerator: LiveNoteGenerating {
    private var results: [Result<String, Error>]
    private var capturedPrompts: [String] = []
    private var remainingSuspendedResponses: Int
    private var responseContinuations: [CheckedContinuation<Void, Never>] = []

    init(results: [Result<String, Error>], suspendFirstResponse: Bool = false, suspendedResponseLimit: Int? = nil) {
        self.results = results
        self.remainingSuspendedResponses = suspendedResponseLimit ?? (suspendFirstResponse ? 1 : 0)
    }

    func generateNote(prompt: String, systemPrompt: String) async throws -> String {
        capturedPrompts.append(prompt)
        let shouldSuspend = remainingSuspendedResponses > 0
        if shouldSuspend {
            remainingSuspendedResponses -= 1
        }

        if shouldSuspend {
            await withCheckedContinuation { continuation in
                responseContinuations.append(continuation)
            }
        }

        guard !results.isEmpty else { throw TestError.missingResult }
        return try results.removeFirst().get()
    }

    func prompts() -> [String] {
        capturedPrompts
    }

    func isResponseSuspended() async -> Bool {
        suspendedResponseCount() > 0
    }

    func suspendedResponseCount() -> Int {
        responseContinuations.count
    }

    func resumeResponse() {
        let continuation = responseContinuations.isEmpty ? nil : responseContinuations.removeFirst()
        continuation?.resume()
    }
}

private actor FakeLiveNoteStorage: LiveNoteStoring {
    private var notes: [LiveNoteRecord]
    private var createdRecords: [LiveNoteRecord] = []
    private var nextId: Int64
    private let createError: Error?
    private let suspendedLoadSessionId: Int64?
    private var loadContinuations: [Int64: CheckedContinuation<Void, Never>] = [:]
    private var loadCallCount = 0

    init(
        existingNotes: [LiveNoteRecord] = [],
        createError: Error? = nil,
        suspendedLoadSessionId: Int64? = nil
    ) {
        self.notes = existingNotes
        self.nextId = (existingNotes.compactMap(\.id).max() ?? 0) + 1
        self.createError = createError
        self.suspendedLoadSessionId = suspendedLoadSessionId
    }

    func createNote(
        sessionId: Int64,
        text: String,
        timestamp: Date,
        isAiGenerated: Bool,
        segmentStartOrder: Int?,
        segmentEndOrder: Int?
    ) async throws -> LiveNoteRecord {
        if let createError {
            throw createError
        }

        let now = Date()
        let record = LiveNoteRecord(
            id: nextId,
            sessionId: sessionId,
            text: text,
            timestamp: timestamp,
            isAiGenerated: isAiGenerated,
            segmentStartOrder: segmentStartOrder,
            segmentEndOrder: segmentEndOrder,
            createdAt: now,
            updatedAt: now
        )
        nextId += 1
        notes.append(record)
        createdRecords.append(record)
        return record
    }

    func updateNote(id: Int64, text: String) async throws {
        guard let index = notes.firstIndex(where: { $0.id == id }) else {
            throw LiveNoteError.noteNotFound
        }
        notes[index].text = text
        notes[index].updatedAt = Date()
    }

    func deleteNote(id: Int64) async throws {
        notes.removeAll { $0.id == id }
    }

    func getLiveNotes(sessionId: Int64) async throws -> [LiveNote] {
        loadCallCount += 1
        if suspendedLoadSessionId == sessionId {
            await withCheckedContinuation { continuation in
                loadContinuations[sessionId] = continuation
            }
        }
        return notes
            .filter { $0.sessionId == sessionId }
            .compactMap { $0.toLiveNote() }
    }

    func createdNotes() -> [LiveNoteRecord] {
        createdRecords
    }

    func getLiveNotesCallCount() -> Int {
        loadCallCount
    }

    func isLoadSuspended(sessionId: Int64) -> Bool {
        loadContinuations[sessionId] != nil
    }

    func resumeLoad(sessionId: Int64) {
        loadContinuations.removeValue(forKey: sessionId)?.resume()
    }
}

private enum TestError: Error {
    case generationFailed
    case missingResult
}
