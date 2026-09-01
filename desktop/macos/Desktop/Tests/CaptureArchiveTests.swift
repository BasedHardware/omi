import Combine
import XCTest

@testable import Omi_Computer

@MainActor
final class CaptureArchiveTests: XCTestCase {
  func testArchiveUsesOnlyOmiSourceForRemoteListAndCount() async {
    let remote = CaptureArchiveRemoteFake(rows: [archiveCapture(id: "omi-1")], count: 1)
    let local = CaptureArchiveLocalFake()
    let repository = CaptureArchiveRepository(remote: remote, local: local)

    await repository.loadInitial()

    XCTAssertEqual(remote.listQueries.count, 1)
    XCTAssertEqual(remote.countQueries.count, 1)
    XCTAssertTrue(remote.listQueries.allSatisfy { $0.source == .omi && !$0.includeDiscarded })
    XCTAssertTrue(remote.countQueries.allSatisfy { $0.source == .omi && !$0.includeDiscarded })
    XCTAssertEqual(remote.listQueries.first?.statuses, [.completed, .processing])
    XCTAssertEqual(repository.captures.map(\.id), ["omi-1"])
  }

  func testArchiveFailureStaysHonestAndNeverRequestsMixedFallback() async {
    let remote = CaptureArchiveRemoteFake(error: ArchiveTestError.offline)
    let local = CaptureArchiveLocalFake(rows: [archiveCapture(id: "cached-omi")], count: 1)
    let repository = CaptureArchiveRepository(remote: remote, local: local)

    await repository.loadInitial()

    XCTAssertEqual(repository.captures.map(\.id), ["cached-omi"])
    XCTAssertNotNil(repository.errorMessage)
    XCTAssertEqual(remote.listQueries.count, 1)
    XCTAssertEqual(remote.listQueries.first?.source, .omi)
    XCTAssertFalse(remote.listQueries.first?.includeDiscarded ?? true)
  }

  func testArchiveRejectsMixedServerRowsInsteadOfClientFilteringThem() async {
    let remote = CaptureArchiveRemoteFake(
      rows: [archiveCapture(id: "omi-1"), archiveCapture(id: "desktop-1", source: .desktop)],
      count: 2
    )
    let repository = CaptureArchiveRepository(remote: remote, local: CaptureArchiveLocalFake())

    await repository.loadInitial()

    XCTAssertTrue(repository.captures.isEmpty)
    XCTAssertNotNil(repository.errorMessage)
    XCTAssertEqual(remote.listQueries.single?.source, .omi)
    XCTAssertEqual(remote.countQueries.single?.source, .omi)
  }

  func testArchiveDoesNotSelectANonOmiGenericCacheDetail() async {
    let nonOmi = archiveCapture(id: "desktop-1", source: .desktop)
    let repository = CaptureArchiveRepository(
      remote: CaptureArchiveRemoteFake(error: ArchiveTestError.offline),
      local: CaptureArchiveLocalFake(rows: [nonOmi], count: 1)
    )

    let detail = await repository.loadDetail(id: nonOmi.id)

    XCTAssertNil(detail)
    XCTAssertNil(repository.selectedCapture)
    XCTAssertNotNil(repository.errorMessage)
  }

  func testOfflineDetailKeepsAValidatedCachedCaptureSelected() async {
    let cached = archiveCapture(id: "cached-omi")
    let repository = CaptureArchiveRepository(
      remote: CaptureArchiveRemoteFake(error: ArchiveTestError.offline),
      local: CaptureArchiveLocalFake(rows: [cached], count: 1)
    )

    let detail = await repository.loadDetail(id: cached.id)

    XCTAssertNil(detail)
    XCTAssertEqual(repository.selectedCapture?.id, cached.id)
    XCTAssertNotNil(repository.errorMessage)
  }

  func testArchivePaginationCarriesOmiQueryAndAdvancesByVisibleRows() async {
    let first = archiveCapture(id: "omi-1")
    let second = archiveCapture(id: "omi-2")
    let remote = CaptureArchiveRemoteFake(rows: [first], count: 2)
    remote.pages = [0: [first], 1: [second]]
    let repository = CaptureArchiveRepository(remote: remote, local: CaptureArchiveLocalFake())

    await repository.loadInitial()
    await repository.loadNextPage()

    XCTAssertEqual(repository.captures.map(\.id), ["omi-1", "omi-2"])
    XCTAssertEqual(remote.listQueries.map(\.offset), [0, 1])
    XCTAssertTrue(remote.listQueries.allSatisfy { $0.source == .omi && !$0.includeDiscarded })
  }

  func testCaptureFocusRoutingOnlyAcknowledgesTheMatchingCanonicalConversationAfterResolution() {
    let focus = ChatFirstPendingFocus.capture(id: "omi-1", momentTs: 18)
    XCTAssertEqual(
      CaptureConversationFocusRoutingPolicy.initialMoment(for: focus, conversationID: "omi-1"),
      18
    )
    XCTAssertNil(CaptureConversationFocusRoutingPolicy.initialMoment(for: focus, conversationID: "omi-2"))
    XCTAssertNil(
      CaptureConversationFocusRoutingPolicy.resolvedFocus(
        for: focus,
        conversationID: "omi-1",
        didResolve: false
      )
    )
    XCTAssertEqual(
      CaptureConversationFocusRoutingPolicy.resolvedFocus(
        for: focus,
        conversationID: "omi-1",
        didResolve: true
      ),
      focus
    )

    let noMoment = ChatFirstPendingFocus.capture(id: "omi-1", momentTs: nil)
    XCTAssertEqual(
      CaptureConversationFocusRoutingPolicy.resolvedFocus(
        for: noMoment,
        conversationID: "omi-1",
        didResolve: true
      ),
      noMoment
    )
  }

  func testRefreshReplacesSelectedCaptureWithTheRefreshedFirstPageRow() async {
    let original = archiveCapture(id: "omi-1", title: "Original title")
    let refreshed = archiveCapture(id: "omi-1", title: "Refreshed title")
    let remote = CaptureArchiveRemoteFake(rows: [original], count: 1)
    let repository = CaptureArchiveRepository(remote: remote, local: CaptureArchiveLocalFake())

    await repository.loadInitial()
    repository.select(original)
    remote.rows = [refreshed]
    await repository.refresh()

    XCTAssertEqual(repository.captures.single?.structured.title, "Refreshed title")
    XCTAssertEqual(repository.selectedCapture?.structured.title, "Refreshed title")
  }

  func testRefreshClearsSelectedCaptureWhenItIsRemovedFromTheFirstPage() async {
    let selected = archiveCapture(id: "omi-1")
    let remote = CaptureArchiveRemoteFake(rows: [selected], count: 1)
    let repository = CaptureArchiveRepository(remote: remote, local: CaptureArchiveLocalFake())

    await repository.loadInitial()
    repository.select(selected)
    remote.rows = []
    remote.count = 0
    await repository.refresh()

    XCTAssertTrue(repository.captures.isEmpty)
    XCTAssertNil(repository.selectedCapture)
  }

  func testClearingSelectionDismissesTheCanonicalDetail() {
    let selected = archiveCapture(id: "omi-1")
    let repository = CaptureArchiveRepository(
      remote: CaptureArchiveRemoteFake(rows: [selected], count: 1),
      local: CaptureArchiveLocalFake()
    )

    repository.select(selected)
    repository.clearSelection()

    XCTAssertNil(repository.selectedCapture)
  }

  func testRuntimeOwnerChangeClearsThePreviousOwnersArchiveProjection() async {
    let capture = archiveCapture(id: "omi-1")
    let remote = CaptureArchiveRemoteFake(rows: [capture], count: 1)
    let repository = CaptureArchiveRepository(
      remote: remote,
      local: CaptureArchiveLocalFake()
    )
    await repository.loadInitial()
    repository.select(capture)

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertTrue(repository.captures.isEmpty)
    XCTAssertNil(repository.selectedCapture)
    XCTAssertNil(repository.count)
    XCTAssertFalse(repository.isLoading)
    XCTAssertNil(repository.errorMessage)

    remote.rows = [archiveCapture(id: "new-owner-omi")]
    await repository.loadInitial()

    XCTAssertEqual(repository.captures.map(\.id), ["new-owner-omi"])
    XCTAssertEqual(remote.listQueries.count, 2)
  }

  func testConversationEndpointIncludesSourceInSharedListAndCountFilters() {
    let listFilters = APIClient.conversationFilterQueryItems(
      statuses: [.completed, .processing],
      sources: [.omi],
      includeDiscarded: false
    )
    let countEndpoint = APIClient.conversationsCountEndpoint(
      includeDiscarded: false,
      statuses: [.completed, .processing],
      sources: [.omi]
    )

    XCTAssertEqual(
      listFilters,
      [
        "include_discarded=false",
        "statuses=completed,processing",
        "sources=omi",
      ])
    XCTAssertTrue(countEndpoint.contains("sources=omi"))
    XCTAssertTrue(countEndpoint.contains("include_discarded=false"))
  }

  func testPlaybackMapsReadyAggregateAndWallOffsets() {
    let response = CaptureAudioURLsResponse(
      audioFiles: [],
      conversationAudio: CaptureAudioURLArtifact(
        status: "cached",
        signedURL: URL(string: "https://example.test/capture.mp3"),
        contentType: "audio/mpeg",
        duration: 40,
        capturedDuration: 45,
        spans: [
          CaptureAudioURLSpan(fileID: "part-a", wallOffset: 12, artifactOffset: 3, length: 10)
        ]
      ),
      pollAfterMs: nil
    )

    guard case .readyAggregate(let artifact) = LiveCapturePlaybackProvider.resolution(from: response) else {
      return XCTFail("Expected aggregate playback artifact")
    }
    XCTAssertEqual(try XCTUnwrap(artifact.artifactOffset(forWallOffset: 17.5)), 8.5, accuracy: 0.001)
    XCTAssertNil(artifact.artifactOffset(forWallOffset: 22))
    XCTAssertEqual(try XCTUnwrap(artifact.wallOffset(forArtifactOffset: 8.5)), 17.5, accuracy: 0.001)
    XCTAssertNil(artifact.wallOffset(forArtifactOffset: 13))
  }

  func testTranscriptFollowMapsPlaybackAcrossAggregateSpansAndFileFallback() {
    let segments = [
      TranscriptSegment(
        id: "first", text: "First", speaker: "SPEAKER_1", isUser: false, personId: nil, start: 12,
        end: 14, translations: []),
      TranscriptSegment(
        id: "second", backendId: "server-second", text: "Second", speaker: "SPEAKER_1", isUser: false,
        personId: nil, start: 17, end: 19, translations: []),
    ]
    let aggregate = CapturePlaybackResolution.readyAggregate(
      CapturePlaybackArtifact(
        signedURL: URL(string: "https://example.test/capture.mp3")!, duration: 40,
        spans: [CaptureAudioURLSpan(fileID: "part-a", wallOffset: 12, artifactOffset: 3, length: 10)]
      ))
    let fallback = CapturePlaybackResolution.fileFallback(
      CapturePlaybackFile(
        id: "part-a", signedURL: URL(string: "https://example.test/part-a.mp3")!, duration: 40
      ))

    XCTAssertEqual(
      CaptureTranscriptFollowPolicy.activeSegmentID(
        atPlaybackOffset: 8.5, resolution: aggregate, segments: segments),
      "server-second"
    )
    XCTAssertNil(
      CaptureTranscriptFollowPolicy.activeSegmentID(
        atPlaybackOffset: 30, resolution: aggregate, segments: segments)
    )
    XCTAssertEqual(
      CaptureTranscriptFollowPolicy.activeSegmentID(
        atPlaybackOffset: 17.5, resolution: fallback, segments: segments),
      "server-second"
    )
  }

  func testPlaybackKeepsPendingLockedUnavailableAndFileFallbackHonest() {
    let pending = CaptureAudioURLsResponse(
      audioFiles: [],
      conversationAudio: CaptureAudioURLArtifact(
        status: "pending", signedURL: nil, contentType: nil, duration: nil, capturedDuration: nil, spans: []
      ),
      pollAfterMs: 3000
    )
    XCTAssertEqual(LiveCapturePlaybackProvider.resolution(from: pending), .pending(pollAfterMs: 3000))

    let unavailable = CaptureAudioURLsResponse(
      audioFiles: [],
      conversationAudio: CaptureAudioURLArtifact(
        status: "unavailable", signedURL: nil, contentType: nil, duration: nil, capturedDuration: nil, spans: []
      ),
      pollAfterMs: nil
    )
    XCTAssertEqual(LiveCapturePlaybackProvider.resolution(from: unavailable), .unavailable)

    let fallback = CaptureAudioURLsResponse(
      audioFiles: [
        CaptureAudioURLFile(
          id: "part-a", status: "cached", signedURL: URL(string: "https://example.test/part-a.mp3"),
          contentType: "audio/mpeg", duration: 12
        )
      ],
      conversationAudio: nil,
      pollAfterMs: nil
    )
    guard case .fileFallback = LiveCapturePlaybackProvider.resolution(from: fallback) else {
      return XCTFail("Expected per-file fallback")
    }
  }

  func testPlaybackCanRefreshAPendingCaptureWithoutChangingItsIdentity() async throws {
    let pending = CapturePlaybackResolution.pending(pollAfterMs: 1_000)
    let ready = CapturePlaybackResolution.fileFallback(
      CapturePlaybackFile(
        id: "part-a", signedURL: try XCTUnwrap(URL(string: "https://example.test/part-a.mp3")), duration: 12
      ))
    let provider = CapturePlaybackProviderFake(resolutions: [pending, ready])
    let controller = CapturePlaybackController(provider: provider)
    let capture = archiveCapture(id: "omi-1")

    let firstResolution = await controller.prepare(for: capture)
    XCTAssertEqual(firstResolution, Optional(pending))
    let refreshedResolution = await controller.prepare(for: capture, forceRefresh: true)
    XCTAssertEqual(refreshedResolution, Optional(ready))
    XCTAssertEqual(provider.resolveCount, 2)
  }

  func testPlaybackTogglePublishesImmediateFeedbackInsteadOfSilentlyDoingNothing() async throws {
    let ready = CapturePlaybackResolution.fileFallback(
      CapturePlaybackFile(
        id: "part-a", signedURL: try XCTUnwrap(URL(string: "https://example.test/part-a.mp3")), duration: 12
      ))
    let controller = CapturePlaybackController(provider: CapturePlaybackProviderFake(resolutions: [ready]))
    let capture = archiveCapture(id: "omi-1")

    _ = await controller.prepare(for: capture)

    XCTAssertTrue(controller.playOrPause())
    XCTAssertTrue(controller.isPlaybackRequested)
    XCTAssertNil(controller.playbackError)

    XCTAssertTrue(controller.playOrPause())
    XCTAssertFalse(controller.isPlaybackRequested)

    controller.clear()
    XCTAssertFalse(controller.playOrPause())
    XCTAssertEqual(controller.playbackError, "Audio is not ready. Check audio and try again.")
  }

  func testPlaybackAdvancesAPlayableAsset() async throws {
    let audioURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("capture-playback-\(UUID().uuidString)")
      .appendingPathExtension("wav")
    defer { try? FileManager.default.removeItem(at: audioURL) }

    try silentWaveData(durationSeconds: 1).write(to: audioURL)

    let ready = CapturePlaybackResolution.fileFallback(
      CapturePlaybackFile(id: "local", signedURL: audioURL, duration: 1)
    )
    let controller = CapturePlaybackController(provider: CapturePlaybackProviderFake(resolutions: [ready]))
    _ = await controller.prepare(for: archiveCapture(id: "omi-local"))

    let playbackAdvanced = expectation(description: "AVPlayer publishes advancing playback time")
    let playbackObservation = controller.$currentTime
      .filter { $0 > 0.1 }
      .prefix(1)
      .sink { _ in playbackAdvanced.fulfill() }

    XCTAssertTrue(controller.playOrPause())
    await fulfillment(of: [playbackAdvanced], timeout: 3)

    XCTAssertNil(controller.playbackError)
    XCTAssertGreaterThan(controller.currentTime, 0.1)
    XCTAssertTrue(controller.isPlaybackRequested)
    withExtendedLifetime(playbackObservation) {}
    controller.clear()
  }

  func testPlaybackClearDiscardsALateResolutionFromThePreviouslySelectedCapture() async throws {
    let provider = DeferredCapturePlaybackProvider()
    let controller = CapturePlaybackController(provider: provider)
    let capture = archiveCapture(id: "omi-a")
    let lateResolution = CapturePlaybackResolution.fileFallback(
      CapturePlaybackFile(
        id: "part-a", signedURL: try XCTUnwrap(URL(string: "https://example.test/part-a.mp3")), duration: 12
      ))

    let preparation = Task { @MainActor in await controller.prepare(for: capture) }
    await provider.waitForRequest(id: capture.id)
    controller.clear()
    await provider.resolve(id: capture.id, with: lateResolution)

    let result = await preparation.value
    XCTAssertNil(result)
    XCTAssertNil(controller.resolution)
    XCTAssertFalse(controller.isResolving)
  }

  func testFocusRequiresSuccessfulAggregateSeekBeforeAcknowledgement() {
    let artifact = CapturePlaybackArtifact(
      signedURL: URL(string: "https://example.test/capture.mp3")!, duration: 20, spans: []
    )
    XCTAssertFalse(
      CaptureFocusAcknowledgementPolicy.canAcknowledge(
        requestedMoment: 3, resolution: .pending(pollAfterMs: 1000)
      ))
    XCTAssertFalse(
      CaptureFocusAcknowledgementPolicy.canAcknowledge(
        requestedMoment: 3,
        resolution: .fileFallback(
          CapturePlaybackFile(
            id: "part", signedURL: URL(string: "https://example.test/part.mp3")!, duration: 3
          )), didCompleteSeek: true
      ))
    XCTAssertFalse(
      CaptureFocusAcknowledgementPolicy.canAcknowledge(
        requestedMoment: 3, resolution: .readyAggregate(artifact), didCompleteSeek: false
      ))
    XCTAssertTrue(
      CaptureFocusAcknowledgementPolicy.canAcknowledge(
        requestedMoment: 3, resolution: .readyAggregate(artifact), didCompleteSeek: true
      ))
  }

}

private func silentWaveData(durationSeconds: Int) -> Data {
  let sampleRate: UInt32 = 44_100
  let channelCount: UInt16 = 1
  let bitsPerSample: UInt16 = 16
  let frameCount = UInt32(durationSeconds) * sampleRate
  let dataSize = frameCount * UInt32(channelCount) * UInt32(bitsPerSample / 8)

  var data = Data()
  func appendASCII(_ value: String) { data.append(contentsOf: value.utf8) }
  func appendLittleEndian<T: FixedWidthInteger>(_ value: T) {
    var littleEndian = value.littleEndian
    withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
  }

  appendASCII("RIFF")
  appendLittleEndian(UInt32(36) + dataSize)
  appendASCII("WAVEfmt ")
  appendLittleEndian(UInt32(16))
  appendLittleEndian(UInt16(1))
  appendLittleEndian(channelCount)
  appendLittleEndian(sampleRate)
  appendLittleEndian(sampleRate * UInt32(channelCount) * UInt32(bitsPerSample / 8))
  appendLittleEndian(channelCount * (bitsPerSample / 8))
  appendLittleEndian(bitsPerSample)
  appendASCII("data")
  appendLittleEndian(dataSize)
  data.append(Data(count: Int(dataSize)))
  return data
}

final class CaptureArchiveCacheTests: XCTestCase {
  private var userID = ""
  private var userDirectory: URL?

  override func setUp() async throws {
    try await super.setUp()
    userID = "capture-archive-cache-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = userID
    await RewindDatabase.shared.configure(userId: userID)
    try await RewindDatabase.shared.initialize()
    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    )
    userDirectory = appSupport.appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent(userID, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDirectory { try? FileManager.default.removeItem(at: userDirectory) }
    try await super.tearDown()
  }

  func testLocalArchiveFiltersOmiAndVisibleStatusesBeforeOrderingAndLimit() async throws {
    let oldOmi = archiveCapture(
      id: "omi-old", source: .omi, status: .completed, createdAt: Date(timeIntervalSince1970: 100)
    )
    let newestDesktop = archiveCapture(
      id: "desktop-new", source: .desktop, status: .completed, createdAt: Date(timeIntervalSince1970: 500)
    )
    let newestInProgressOmi = archiveCapture(
      id: "omi-in-progress", source: .omi, status: .inProgress, createdAt: Date(timeIntervalSince1970: 400)
    )
    let processingOmi = archiveCapture(
      id: "omi-processing", source: .omi, status: .processing, createdAt: Date(timeIntervalSince1970: 300)
    )
    for capture in [oldOmi, newestDesktop, newestInProgressOmi, processingOmi] {
      _ = try await TranscriptionStorage.shared.syncServerConversation(capture)
    }

    let firstPage = try await TranscriptionStorage.shared.getLocalOmiCaptureConversations(limit: 1)
    let allRows = try await TranscriptionStorage.shared.getLocalOmiCaptureConversations(limit: 10)
    let count = try await TranscriptionStorage.shared.getLocalOmiCaptureConversationsCount()

    XCTAssertEqual(firstPage.map(\.id), ["omi-processing"])
    XCTAssertEqual(allRows.map(\.id), ["omi-processing", "omi-old"])
    XCTAssertEqual(count, 2)
  }
}

private enum ArchiveTestError: Error {
  case offline
}

private func archiveCapture(
  id: String,
  source: ConversationSource = .omi,
  status: ConversationStatus = .completed,
  createdAt: Date = Date(timeIntervalSince1970: 100),
  title: String? = nil
) -> ServerConversation {
  ServerConversation(
    id: id,
    createdAt: createdAt,
    updatedAt: createdAt,
    startedAt: createdAt,
    finishedAt: createdAt.addingTimeInterval(60),
    structured: Structured(
      title: title ?? "Capture \(id)", overview: "Summary", emoji: "", category: "other", actionItems: [], events: []),
    transcriptSegments: [],
    transcriptSegmentsIncluded: false,
    geolocation: nil,
    photos: [],
    appsResults: [],
    source: source,
    language: "en",
    status: status,
    discarded: false,
    deleted: false,
    isLocked: false,
    starred: false,
    folderId: nil,
    inputDeviceName: nil
  )
}

@MainActor
private final class CaptureArchiveRemoteFake: CaptureArchiveRemoteDataSource {
  var listQueries: [CaptureArchiveQuery] = []
  var countQueries: [CaptureArchiveQuery] = []
  var rows: [ServerConversation]
  var count: Int
  var pages: [Int: [ServerConversation]] = [:]
  var error: Error?

  init(rows: [ServerConversation] = [], count: Int = 0, error: Error? = nil) {
    self.rows = rows
    self.count = count
    self.error = error
  }

  func list(query: CaptureArchiveQuery) async throws -> [ServerConversation] {
    listQueries.append(query)
    if let error { throw error }
    return pages[query.offset] ?? rows
  }

  func count(query: CaptureArchiveQuery) async throws -> Int {
    countQueries.append(query)
    if let error { throw error }
    return count
  }

  func detail(id: String) async throws -> ServerConversation {
    if let error { throw error }
    guard let capture = rows.first(where: { $0.id == id }) else { throw ArchiveTestError.offline }
    return capture
  }
}

private final class CaptureArchiveLocalFake: CaptureArchiveLocalDataSource, @unchecked Sendable {
  var rows: [ServerConversation]
  var countValue: Int

  init(rows: [ServerConversation] = [], count: Int = 0) {
    self.rows = rows
    countValue = count
  }

  func list(query: CaptureArchiveQuery) async throws -> [ServerConversation] { rows }
  func count(query: CaptureArchiveQuery) async throws -> Int { countValue }
  func detail(id: String) async throws -> ServerConversation? { rows.first { $0.id == id } }
  func store(_ conversation: ServerConversation) async throws {}
}

private final class CapturePlaybackProviderFake: CapturePlaybackProviding, @unchecked Sendable {
  private var resolutions: [CapturePlaybackResolution]
  private(set) var resolveCount = 0

  init(resolutions: [CapturePlaybackResolution]) {
    self.resolutions = resolutions
  }

  func resolvePlayback(for capture: ServerConversation) async -> CapturePlaybackResolution {
    resolveCount += 1
    return resolutions.removeFirst()
  }
}

private actor DeferredCapturePlaybackProvider: CapturePlaybackProviding {
  private var pending: [String: CheckedContinuation<CapturePlaybackResolution, Never>] = [:]
  private var requestWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]

  func resolvePlayback(for capture: ServerConversation) async -> CapturePlaybackResolution {
    let waiters = requestWaiters.removeValue(forKey: capture.id) ?? []
    for waiter in waiters {
      waiter.resume()
    }
    return await withCheckedContinuation { continuation in
      pending[capture.id] = continuation
    }
  }

  func waitForRequest(id: String) async {
    guard pending[id] == nil else { return }
    await withCheckedContinuation { continuation in
      requestWaiters[id, default: []].append(continuation)
    }
  }

  func resolve(id: String, with resolution: CapturePlaybackResolution) {
    pending.removeValue(forKey: id)?.resume(returning: resolution)
  }
}

extension Array {
  fileprivate var single: Element? { count == 1 ? first : nil }
}
