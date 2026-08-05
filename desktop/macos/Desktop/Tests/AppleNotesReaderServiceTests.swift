import XCTest

@testable import Omi_Computer

// MARK: - Test doubles

/// Scripted `osascript` stand-in. It records every invocation so a test can
/// assert *which* scripts production code ran, how many times, and with what
/// bounds — the properties that broke when the reader fetched notes one at a
/// time or paid for the body export it did not need.
actor FakeAppleNotesScriptRunner: AppleNotesScriptRunning {
  struct Invocation: Sendable, Equatable {
    let source: String
    let environment: [String: String]
    let timeoutSeconds: TimeInterval
  }

  enum Response: Sendable {
    case payload(Data)
    case exit(status: Int32, stderr: String)
    case transportFailure(AppleNotesScriptRunnerError)
  }

  private let manifestResponse: Response
  private let fullExportResponse: Response
  private(set) var invocations: [Invocation] = []

  init(manifest: Response = .payload(Data()), fullExport: Response = .payload(Data())) {
    self.manifestResponse = manifest
    self.fullExportResponse = fullExport
  }

  func run(
    source: String,
    environment: [String: String],
    timeoutSeconds: TimeInterval
  ) async throws -> AppleNotesScriptResult {
    invocations.append(
      Invocation(source: source, environment: environment, timeoutSeconds: timeoutSeconds))
    let response = source == AppleNotesScript.manifest ? manifestResponse : fullExportResponse
    switch response {
    case .payload(let data):
      return AppleNotesScriptResult(stdout: data, stderr: "", terminationStatus: 0, duration: 0.01)
    case .exit(let status, let stderr):
      return AppleNotesScriptResult(stdout: Data(), stderr: stderr, terminationStatus: status, duration: 0.01)
    case .transportFailure(let error):
      throw error
    }
  }
}

actor FakeAppleNotesAutomationGate: AppleNotesAutomationGate {
  private let status: OSStatus
  private let launchSucceeds: Bool
  private var running: Bool
  private(set) var launchCount = 0

  init(status: OSStatus = noErr, running: Bool = true, launchSucceeds: Bool = true) {
    self.status = status
    self.running = running
    self.launchSucceeds = launchSucceeds
  }

  func permissionStatus() async -> OSStatus { status }

  func isNotesRunning() async -> Bool { running }

  func launchNotesInBackground() async -> Bool {
    launchCount += 1
    if launchSucceeds { running = true }
    return launchSucceeds
  }
}

actor InMemoryAppleNotesSyncStateStore: AppleNotesSyncStateStoring {
  private var state: AppleNotesSyncState?
  private(set) var saveCount = 0

  init(state: AppleNotesSyncState? = nil) {
    self.state = state
  }

  func load() async -> AppleNotesSyncState? { state }

  func save(_ newState: AppleNotesSyncState) async {
    state = newState
    saveCount += 1
  }

  func clear() async { state = nil }

  func persistedState() -> AppleNotesSyncState? { state }
}

actor RecordingDiagnosticsSink: AppleNotesDiagnosticsRecording {
  struct Record: Sendable, Equatable {
    let area: String
    let from: String
    let to: String
    let reason: String
    let outcome: String
  }

  private(set) var records: [Record] = []

  func recordFallback(
    area: String,
    from: String,
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome
  ) async {
    records.append(Record(area: area, from: from, to: to, reason: reason, outcome: outcome.rawValue))
  }
}

// MARK: - Tests

final class AppleNotesReaderServiceTests: XCTestCase {
  private let fixedNow = Date(timeIntervalSince1970: 1_800_000_000)

  // MARK: Full library reads

  func testImportsEveryNoteInTheScriptPayload() async throws {
    // Regression guard: the store-scraping reader imported 75 of 836 notes
    // because attachment heuristics and a folder filter silently dropped the
    // rest. Every note the script reports must survive into the import.
    let runner = FakeAppleNotesScriptRunner(fullExport: .payload(try fixtureData("full-836.json")))
    let service = makeService(runner: runner)

    let notes = try await service.readAllNotes(userInitiated: true)

    XCTAssertEqual(notes.count, 836)
    XCTAssertEqual(Set(notes.map(\.id)).count, 836, "note keys must stay unique across the library")
  }

  func testReturnsFullBodyNotJustTitleAndSnippet() async throws {
    let payload = try fixtureData("full-836.json")
    let expected = try XCTUnwrap(try fixtureNotes(payload).first)
    let expectedBody = try XCTUnwrap(expected["body"] as? String)
    let service = makeService(runner: FakeAppleNotesScriptRunner(fullExport: .payload(payload)))

    let notes = try await service.readAllNotes(userInitiated: true)
    let first = try XCTUnwrap(notes.first)

    XCTAssertEqual(first.body, expectedBody)
    XCTAssertNotEqual(first.body, first.title)
    XCTAssertFalse(first.bodyTruncated)
    XCTAssertGreaterThan(first.body.count, first.title.count)
  }

  func testTruncatesOversizedBodyAndMarksIt() async throws {
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(fullExport: .payload(try fixtureData("full-oversized-body.json"))))

    let notes = try await service.readAllNotes(maxBodyChars: 8_000, userInitiated: true)

    let oversized = try XCTUnwrap(notes.first)
    XCTAssertEqual(oversized.body.count, 8_000)
    XCTAssertTrue(oversized.bodyTruncated)

    let short = try XCTUnwrap(notes.last)
    XCTAssertLessThan(short.body.count, 8_000)
    XCTAssertFalse(short.bodyTruncated)
  }

  func testSkipsPasswordProtectedNotes() async throws {
    let payload = try fixtureData("full-with-locked.json")
    let exportedKeys = try fixtureKeys(payload)
    let lockedKeys = ["p2900", "p2901"]
    let runner = FakeAppleNotesScriptRunner(
      manifest: .payload(try manifestPayload(keys: exportedKeys + lockedKeys)),
      fullExport: .payload(payload)
    )
    let service = makeService(runner: runner)

    let result = try await service.syncChangedNotes(userInitiated: true)

    XCTAssertEqual(result.lockedSkipped, 2)
    XCTAssertEqual(result.changed.count, exportedKeys.count)
    XCTAssertEqual(result.totalNotes, exportedKeys.count + lockedKeys.count)
    XCTAssertTrue(result.changed.allSatisfy { !lockedKeys.contains($0.id) })
  }

  func testNeverFetchesNotesOneAtATime() async throws {
    // Per-note `notes.byId(id)` costs ~0.31s each versus ~0.61s for the whole
    // bulk export. Only the two bulk scripts may ever cross the boundary.
    let runner = FakeAppleNotesScriptRunner(
      manifest: .payload(try fixtureData("manifest-836.json")),
      fullExport: .payload(try fixtureData("full-836.json"))
    )
    let service = makeService(runner: runner)

    _ = try await service.syncChangedNotes(userInitiated: true)

    let invocations = await runner.invocations
    XCTAssertFalse(invocations.isEmpty)
    for invocation in invocations {
      XCTAssertTrue(
        invocation.source == AppleNotesScript.manifest || invocation.source == AppleNotesScript.fullExport,
        "an unexpected script crossed the process boundary"
      )
      XCTAssertFalse(invocation.source.contains(".byId("), "per-note lookups are ~500x slower than the bulk export")
    }
  }

  // MARK: Incremental sync

  func testIncrementalSyncSkipsBodyFetchWhenManifestUnchanged() async throws {
    let manifest = try fixtureData("manifest-836.json")
    let store = InMemoryAppleNotesSyncStateStore(state: try syncState(matching: manifest))
    let runner = FakeAppleNotesScriptRunner(
      manifest: .payload(manifest),
      fullExport: .payload(try fixtureData("full-836.json"))
    )
    let service = makeService(runner: runner, syncState: store)

    let result = try await service.syncChangedNotes(userInitiated: true)

    XCTAssertTrue(result.changed.isEmpty)
    XCTAssertEqual(result.totalNotes, 836)
    let invocations = await runner.invocations
    XCTAssertEqual(invocations.count, 1, "an unchanged manifest must not pay for the body export")
    XCTAssertEqual(invocations.first?.source, AppleNotesScript.manifest)
  }

  func testIncrementalSyncReturnsOnlyChangedNotes() async throws {
    let manifest = try fixtureData("manifest-836.json")
    var state = try syncState(matching: manifest)
    let staleKey = try XCTUnwrap(try fixtureKeys(manifest).first)
    let stored = try XCTUnwrap(state.entries[staleKey])
    state.entries[staleKey] = AppleNotesSyncState.Entry(
      modifiedAt: stored.modifiedAt.addingTimeInterval(-3_600),
      contentHash: "stale-hash"
    )
    let store = InMemoryAppleNotesSyncStateStore(state: state)
    let runner = FakeAppleNotesScriptRunner(
      manifest: .payload(manifest),
      fullExport: .payload(try fixtureData("full-836.json"))
    )
    let service = makeService(runner: runner, syncState: store)

    let result = try await service.syncChangedNotes(userInitiated: true)

    let invocationCount = await runner.invocations.count
    XCTAssertEqual(result.changed.map(\.id), [staleKey])
    XCTAssertEqual(invocationCount, 2)
  }

  func testIncrementalSyncIgnoresMtimeBumpWithIdenticalContent() async throws {
    // Notes bumps a note's modification date on folder moves. Identical content
    // must not be re-imported just because the timestamp moved.
    let payload = try fixtureData("full-with-locked.json")
    let notes = try fixtureNotes(payload)
    var entries: [String: AppleNotesSyncState.Entry] = [:]
    for note in notes {
      let key = AppleNotesSyncState.noteKey(fromAppleScriptID: try XCTUnwrap(note["id"] as? String))
      entries[key] = AppleNotesSyncState.Entry(
        modifiedAt: Date(timeIntervalSince1970: 1),
        contentHash: AppleNotesSyncState.contentHash(
          title: try XCTUnwrap(note["title"] as? String),
          body: try XCTUnwrap(note["body"] as? String)
        )
      )
    }
    let store = InMemoryAppleNotesSyncStateStore(
      state: AppleNotesSyncState(lastSyncedAt: fixedNow, entries: entries))
    let runner = FakeAppleNotesScriptRunner(
      manifest: .payload(try manifestPayload(keys: Array(entries.keys))),
      fullExport: .payload(payload)
    )
    let service = makeService(runner: runner, syncState: store)

    let result = try await service.syncChangedNotes(userInitiated: true)

    let invocationCount = await runner.invocations.count
    XCTAssertTrue(result.changed.isEmpty, "identical content must not be re-imported after an mtime bump")
    XCTAssertEqual(invocationCount, 2, "the body export is what proves the content is unchanged")
  }

  func testUnreadableSyncStateFallsBackToFullResyncAndRecordsFallback() async throws {
    let payload = try fixtureData("full-with-locked.json")
    let keys = try fixtureKeys(payload)
    let sink = RecordingDiagnosticsSink()
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(
        manifest: .payload(try manifestPayload(keys: keys)),
        fullExport: .payload(payload)
      ),
      syncState: InMemoryAppleNotesSyncStateStore(state: nil),
      diagnostics: sink
    )

    let result = try await service.syncChangedNotes(userInitiated: true)

    XCTAssertEqual(result.changed.count, keys.count)
    let records = await sink.records
    XCTAssertEqual(
      records,
      [
        RecordingDiagnosticsSink.Record(
          area: "connector_sync",
          from: "incremental",
          to: "full_resync",
          reason: "sync_state_unreadable",
          outcome: "recovered"
        )
      ]
    )
  }

  func testSchemaVersionMismatchForcesFullResync() async throws {
    let directory = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: directory) }

    let payload = try fixtureData("full-with-locked.json")
    let keys = try fixtureKeys(payload)
    let manifest = try manifestPayload(keys: keys)
    let futureState = AppleNotesSyncState(
      schemaVersion: AppleNotesScript.schemaVersion + 98,
      lastSyncedAt: fixedNow,
      entries: try syncState(matching: manifest).entries
    )
    let store = FileAppleNotesSyncStateStore(directory: directory)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try JSONEncoder().encode(futureState).write(to: store.fileURL)

    let mismatchedLoad = await store.load()
    XCTAssertNil(mismatchedLoad, "a payload written by a different schema is not usable state")

    let sink = RecordingDiagnosticsSink()
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(manifest: .payload(manifest), fullExport: .payload(payload)),
      syncState: store,
      diagnostics: sink
    )

    let result = try await service.syncChangedNotes(userInitiated: true)

    let fallbackTargets = await sink.records.map(\.to)
    XCTAssertEqual(result.changed.count, keys.count)
    XCTAssertEqual(fallbackTargets, ["full_resync"])
  }

  func testDeletedNotesAreReportedNotDeletedRemotely() async throws {
    let payload = try fixtureData("full-with-locked.json")
    let manifest = try manifestPayload(keys: try fixtureKeys(payload))
    var state = try syncState(matching: manifest)
    state.entries["p9999"] = AppleNotesSyncState.Entry(
      modifiedAt: Date(timeIntervalSince1970: 5), contentHash: "gone")
    let store = InMemoryAppleNotesSyncStateStore(state: state)
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(manifest: .payload(manifest), fullExport: .payload(payload)),
      syncState: store
    )

    let result = try await service.syncChangedNotes(userInitiated: true)

    XCTAssertEqual(result.deletedKeys, ["p9999"])
    XCTAssertTrue(result.changed.isEmpty, "a deletion is reported, never emitted as changed evidence")
    let persistedState = await store.persistedState()
    let persisted = try XCTUnwrap(persistedState)
    XCTAssertNil(persisted.entries["p9999"], "local tracking stops; remote evidence is left alone")
  }

  func testExternalIdIsStableWhenTheStoreUUIDChanges() async throws {
    // A CoreData store rebuild (iCloud re-sync, OS migration) mints a new store
    // UUID. Keying on the whole AppleScript id would reset every external id and
    // re-import the entire library as new evidence.
    let firstStore = "11111111-1111-4111-8111-111111111111"
    let secondStore = "22222222-2222-4222-8222-222222222222"

    let before = try await makeService(
      runner: FakeAppleNotesScriptRunner(fullExport: .payload(try exportPayload(storeUUID: firstStore)))
    )
    .readAllNotes(userInitiated: true)
    let after = try await makeService(
      runner: FakeAppleNotesScriptRunner(fullExport: .payload(try exportPayload(storeUUID: secondStore)))
    )
    .readAllNotes(userInitiated: true)

    XCTAssertEqual(before.map(\.id), ["p1443"])
    XCTAssertEqual(before.map(\.id), after.map(\.id))
    XCTAssertEqual(
      "apple_notes:\(try XCTUnwrap(before.first).id)",
      "apple_notes:\(try XCTUnwrap(after.first).id)"
    )
  }

  func testFolderSkipModeRecordsFallbackAndOmitsFolder() async throws {
    let sink = RecordingDiagnosticsSink()
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(fullExport: .payload(try fixtureData("folders-skipped.json"))),
      diagnostics: sink
    )

    let notes = try await service.readAllNotes(userInitiated: true)

    XCTAssertFalse(notes.isEmpty)
    XCTAssertTrue(notes.allSatisfy { $0.folder == nil }, "a skipped folder mode means unknown, not empty")
    let records = await sink.records
    XCTAssertEqual(
      records,
      [
        RecordingDiagnosticsSink.Record(
          area: "connector_sync",
          from: "folders_mapped",
          to: "folders_skipped",
          reason: "policy",
          outcome: "degraded"
        )
      ]
    )
  }

  // MARK: Failure handling

  func testTimeoutClassifiesAsReadTimedOut() async throws {
    let sink = RecordingDiagnosticsSink()
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(fullExport: .transportFailure(.timedOut(seconds: 90))),
      diagnostics: sink
    )

    do {
      _ = try await service.readAllNotes(userInitiated: true)
      XCTFail("expected the read to fail")
    } catch let error as AppleNotesReaderError {
      XCTAssertEqual(error, .readTimedOut(seconds: 90))
      XCTAssertEqual(error.reasonCode, "notes_read_timed_out")
      XCTAssertFalse(error.shouldPromptForAutomationPermission)
    }

    let records = await sink.records
    XCTAssertTrue(records.isEmpty, "a timeout is a hard failure, not a fallback")
  }

  func testPermissionDeniedIsNeedsAccessAndPromptsForAutomation() async {
    let service = makeService(gate: FakeAppleNotesAutomationGate(status: -1743))

    let status = await service.connectionStatus(userInitiated: true)

    guard case .needsAccess(_, let reasonCode) = status else {
      return XCTFail("expected needsAccess, got \(status)")
    }
    XCTAssertEqual(reasonCode, "automation_permission_denied")
    XCTAssertTrue(AppleNotesReaderError.automationPermissionDenied.shouldPromptForAutomationPermission)
  }

  func testPassiveSyncNeverLaunchesNotesWhenPermissionIsNotGranted() async {
    let gate = FakeAppleNotesAutomationGate(status: -1744, running: false)
    let runner = FakeAppleNotesScriptRunner()
    let service = makeService(runner: runner, gate: gate)

    do {
      _ = try await service.syncChangedNotes(userInitiated: false)
      XCTFail("a passive sync must not proceed without granted automation permission")
    } catch let error as AppleNotesReaderError {
      XCTAssertEqual(error, .automationPermissionUndetermined)
    } catch {
      XCTFail("unexpected error \(error)")
    }

    let launchCount = await gate.launchCount
    let invocations = await runner.invocations
    XCTAssertEqual(launchCount, 0, "a passive read must never launch Notes to force a prompt")
    XCTAssertTrue(invocations.isEmpty)
  }

  func testUserInitiatedReadLaunchesNotesWhenNotRunning() async throws {
    let gate = FakeAppleNotesAutomationGate(status: noErr, running: false)
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(fullExport: .payload(try fixtureData("full-with-locked.json"))),
      gate: gate
    )

    let notes = try await service.readAllNotes(userInitiated: true)

    let launchCount = await gate.launchCount
    XCTAssertFalse(notes.isEmpty)
    XCTAssertEqual(launchCount, 1, "a user-initiated read starts Notes without stealing focus")
  }

  func testClampsResultAndBodyBoundsBeforeCrossingTheProcessBoundary() async throws {
    let runner = FakeAppleNotesScriptRunner(fullExport: .payload(try fixtureData("full-836.json")))
    let service = makeService(runner: runner)

    let none = try await service.readAllNotes(maxResults: -1, userInitiated: true)
    let invocationsAfterClamp = await runner.invocations
    XCTAssertTrue(none.isEmpty)
    XCTAssertTrue(invocationsAfterClamp.isEmpty, "a non-positive limit must not launch a helper process")

    _ = try await service.readAllNotes(maxBodyChars: -5, userInitiated: true)

    let lastInvocation = await runner.invocations.last
    let environment = try XCTUnwrap(lastInvocation?.environment)
    let bodyChars = try XCTUnwrap(Int(try XCTUnwrap(environment[AppleNotesScript.maxBodyCharsEnvironmentKey])))
    let folders = try XCTUnwrap(Int(try XCTUnwrap(environment[AppleNotesScript.maxFoldersEnvironmentKey])))
    XCTAssertGreaterThan(bodyChars, 0)
    XCTAssertGreaterThan(folders, 0)
  }

  func testConnectionStatusTreatsZeroNotesAsReadable() async throws {
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(manifest: .payload(try fixtureData("empty-library.json"))))

    let status = await service.connectionStatus(userInitiated: true)

    guard case .connected(let noteCount, _) = status else {
      return XCTFail("an empty library is a working connector, got \(status)")
    }
    XCTAssertEqual(noteCount, 0)
    XCTAssertTrue(status.isConnected)
  }

  func testConnectionStatusSurfacesMalformedOutputAsError() async throws {
    let service = makeService(
      runner: FakeAppleNotesScriptRunner(manifest: .payload(try fixtureData("malformed-truncated.json"))))

    let status = await service.connectionStatus(userInitiated: true)

    guard case .error(_, let reasonCode) = status else {
      return XCTFail("expected an error status, got \(status)")
    }
    XCTAssertEqual(reasonCode, "malformed_response")
  }

  func testClassifiesAppleEventErrorCodes() {
    XCTAssertEqual(
      AppleNotesOutcomeParser.classify(stderr: "execution error: Not authorized. (-1743)", terminationStatus: 1),
      .automationPermissionDenied
    )
    XCTAssertEqual(
      AppleNotesOutcomeParser.classify(stderr: "execution error: (-1744)", terminationStatus: 1),
      .automationPermissionUndetermined
    )
    XCTAssertEqual(
      AppleNotesOutcomeParser.classify(
        stderr: "execution error: Application isn't running. (-600)", terminationStatus: 1),
      .notesAppUnavailable
    )
    XCTAssertEqual(
      AppleNotesOutcomeParser.classify(stderr: "execution error: Can't get application. (-2700)", terminationStatus: 1),
      .notesAppUnavailable
    )
    XCTAssertEqual(
      AppleNotesOutcomeParser.classify(stderr: "boom", terminationStatus: 2),
      .readFailed(reason: "boom")
    )
    XCTAssertEqual(
      AppleNotesOutcomeParser.classify(stderr: "", terminationStatus: 3).reasonCode,
      "notes_read_failed"
    )
    XCTAssertEqual(AppleNotesReaderError.readTimedOut(seconds: 20).reasonCode, "notes_read_timed_out")
  }

  func testReadOutcomeClassifiesPermissionFailuresAsNeedsAccess() {
    for error in [
      AppleNotesReaderError.automationPermissionDenied,
      AppleNotesReaderError.automationPermissionUndetermined,
    ] {
      XCTAssertEqual(
        AppleNotesReaderService.classifyReadOutcome(noteCount: nil, error: error),
        .needsAccess(message: error.localizedDescription, reasonCode: error.reasonCode)
      )
    }

    XCTAssertEqual(
      AppleNotesReaderService.classifyReadOutcome(noteCount: 0, error: nil),
      .readable(noteCount: 0)
    )
  }

  func testReadOutcomeClassifiesMalformedAndReadFailuresAsErrors() {
    for error in [
      AppleNotesReaderError.malformedResponse(reason: "unsupported payload schema 7"),
      AppleNotesReaderError.readFailed(reason: "concurrent_modification"),
      AppleNotesReaderError.readTimedOut(seconds: 90),
      AppleNotesReaderError.notesAppUnavailable,
      AppleNotesReaderError.passiveReadDeclined,
    ] {
      XCTAssertEqual(
        AppleNotesReaderService.classifyReadOutcome(noteCount: nil, error: error),
        .error(message: error.localizedDescription, reasonCode: error.reasonCode)
      )
    }

    XCTAssertEqual(AppleNotesReaderError.passiveReadDeclined.reasonCode, "user_initiated_read_required")
  }

  // MARK: Digest + persistence

  func testSynthesisDigestIsBoundedInNoteCountAndPerNoteLength() {
    let filler = String(repeating: "lorem ipsum ", count: 700)
    XCTAssertGreaterThan(filler.count, 8_000)
    let notes = (0..<500).map { index in
      AppleNoteRecord(
        id: "p\(index)",
        title: "Lorem note \(index)",
        body: String(filler.prefix(8_000)),
        bodyTruncated: true,
        folder: nil,
        createdAt: fixedNow,
        modifiedAt: fixedNow
      )
    }

    let digest = AppleNotesReaderService.synthesisDigest(notes)
    let entries = digest.components(separatedBy: "\n---\n")

    XCTAssertLessThanOrEqual(entries.count, 120)
    XCTAssertEqual(entries.count, 120)
    for entry in entries {
      let excerpt = entry.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false).last ?? ""
      XCTAssertLessThanOrEqual(excerpt.count, 300)
    }
    XCTAssertLessThan(digest.utf8.count, 64 * 1_024)
  }

  func testSyncStateRoundTripsThroughTheFileStore() async throws {
    let directory = try makeTemporaryDirectory()
    defer { try? FileManager.default.removeItem(at: directory) }

    let store = FileAppleNotesSyncStateStore(directory: directory)
    let missingLoad = await store.load()
    XCTAssertNil(missingLoad, "a missing file is unusable state, not an empty state")

    let state = AppleNotesSyncState(
      lastSyncedAt: fixedNow,
      entries: [
        "p1443": AppleNotesSyncState.Entry(
          modifiedAt: Date(timeIntervalSince1970: 1_799_999_999.25),
          contentHash: AppleNotesSyncState.contentHash(title: "Lorem", body: "ipsum dolor")
        )
      ]
    )
    await store.save(state)

    let roundTripped = await store.load()
    let loaded = try XCTUnwrap(roundTripped)
    XCTAssertEqual(loaded, state, "the diff compares timestamps for equality, so persistence must be lossless")

    try Data("not json at all".utf8).write(to: store.fileURL)
    let corruptLoad = await store.load()
    XCTAssertNil(corruptLoad, "a corrupt file must force a full resync, not a partial diff")

    await store.clear()
    let clearedLoad = await store.load()
    XCTAssertNil(clearedLoad)
  }

  // MARK: - Helpers

  private func makeService(
    runner: AppleNotesScriptRunning = FakeAppleNotesScriptRunner(),
    gate: AppleNotesAutomationGate = FakeAppleNotesAutomationGate(),
    syncState: AppleNotesSyncStateStoring = InMemoryAppleNotesSyncStateStore(),
    diagnostics: AppleNotesDiagnosticsRecording = RecordingDiagnosticsSink()
  ) -> AppleNotesReaderService {
    let timestamp = fixedNow
    return AppleNotesReaderService(
      runner: runner,
      gate: gate,
      syncState: syncState,
      diagnostics: diagnostics,
      now: { timestamp }
    )
  }

  /// Captured script payloads. They carry lorem text only — never real notes.
  private func fixtureData(_ name: String) throws -> Data {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .appendingPathComponent("fixtures/AppleNotes", isDirectory: true)
      .appendingPathComponent(name, isDirectory: false)
    return try Data(contentsOf: url)
  }

  private func fixtureNotes(_ data: Data) throws -> [[String: Any]] {
    let payload = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
    return try XCTUnwrap(payload["notes"] as? [[String: Any]])
  }

  private func fixtureKeys(_ data: Data) throws -> [String] {
    try fixtureNotes(data).map { note in
      AppleNotesSyncState.noteKey(fromAppleScriptID: (note["id"] as? String) ?? "")
    }
  }

  /// Builds sync state that exactly matches a manifest payload, i.e. the state a
  /// previous successful pass would have left behind.
  private func syncState(matching manifest: Data) throws -> AppleNotesSyncState {
    var entries: [String: AppleNotesSyncState.Entry] = [:]
    for note in try fixtureNotes(manifest) {
      let key = AppleNotesSyncState.noteKey(fromAppleScriptID: (note["id"] as? String) ?? "")
      entries[key] = AppleNotesSyncState.Entry(
        modifiedAt: try isoDate(XCTUnwrap(note["modifiedAt"] as? String)),
        contentHash: "already-imported-\(key)"
      )
    }
    return AppleNotesSyncState(lastSyncedAt: fixedNow, entries: entries)
  }

  private func manifestPayload(keys: [String]) throws -> Data {
    let notes = keys.enumerated().map { index, key in
      [
        "id": "x-coredata://33333333-3333-4333-8333-333333333333/ICNote/\(key)",
        "modifiedAt": manifestTimestamps[index % manifestTimestamps.count],
      ]
    }
    return try JSONSerialization.data(withJSONObject: ["schema": 1, "notes": notes])
  }

  private func exportPayload(storeUUID: String) throws -> Data {
    let payload: [String: Any] = [
      "schema": 1,
      "lockedSkipped": 0,
      "folderMode": "mapped",
      "notes": [
        [
          "id": "x-coredata://\(storeUUID)/ICNote/p1443",
          "title": "Lorem stable identity",
          "body": "lorem ipsum dolor sit amet consectetur",
          "truncated": false,
          "modifiedAt": "2026-03-04T10:15:00.000Z",
          "createdAt": "2026-03-01T09:00:00.000Z",
          "folder": "Notes",
        ]
      ],
    ]
    return try JSONSerialization.data(withJSONObject: payload)
  }

  private let manifestTimestamps = [
    "2026-01-04T10:15:00.000Z",
    "2026-01-05T11:16:00.000Z",
    "2026-01-06T12:17:00.000Z",
    "2026-01-07T13:18:00.000Z",
    "2026-01-08T14:19:00.000Z",
    "2026-01-09T15:20:00.000Z",
  ]

  private func isoDate(_ text: String) throws -> Date {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return try XCTUnwrap(formatter.date(from: text))
  }

  private func makeTemporaryDirectory() throws -> URL {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("AppleNotesReaderServiceTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
  }
}
