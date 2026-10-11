import Foundation
import XCTest

@testable import Omi_Computer

@MainActor
final class ProgressiveTTSPlaybackPipelineTests: XCTestCase {
  func testPlaybackStartsBeforeSlowStreamCompletes() async {
    let source = ControlledTTSStreamSource()
    let players = FakeProgressivePlayerStore()
    let started = expectation(description: "playback started from first drip")
    let pipeline = makePipeline(source: source, players: players)
    pipeline.onPlaybackStarted = { _ in started.fulfill() }

    pipeline.enqueue("first chunk")
    await source.waitUntilRequested("first chunk")
    await source.yield(Data(repeating: 1, count: 4_096), to: "first chunk")
    await fulfillment(of: [started], timeout: 1)

    let streamFinished = await source.isFinished("first chunk")
    XCTAssertFalse(streamFinished)
    XCTAssertEqual(players.created.count, 1)
    XCTAssertFalse(players.created[0].didFinishInput)

    await source.finish("first chunk")
    await waitUntil { players.created[0].didFinishInput }
    players.created[0].drain()
    await waitUntil { !pipeline.isActive }
  }

  func testMidStreamFailureDrainsArrivedAudioThenFallsBackToUntouchedSuffix() async {
    let source = ControlledTTSStreamSource()
    let players = FakeProgressivePlayerStore()
    let fallback = expectation(description: "suffix fallback")
    let text = "one two three four five six seven eight nine ten eleven twelve"
    var fallbackText: String?
    let pipeline = makePipeline(source: source, players: players)
    pipeline.onFallback = { text, _, completion in
      fallbackText = text
      completion()
      fallback.fulfill()
    }

    pipeline.enqueue(text)
    await source.waitUntilRequested(text)
    await source.yield(Data([1, 2, 3]), to: text)
    await waitUntil { players.created.first?.didStart == true }
    await source.fail(TestStreamError.disconnected, text: text)
    await waitUntil { players.created[0].didFinishInput }

    XCTAssertNil(fallbackText, "fallback must wait for already queued audio to drain")
    players.created[0].drain(playedMediaDuration: 1)
    await fulfillment(of: [fallback], timeout: 1)

    XCTAssertEqual(fallbackText, "seven eight nine ten eleven twelve")
    XCTAssertFalse(pipeline.isActive)
  }

  func testCancelStopsPlayerAndTerminatesNetworkStreamWithoutFallback() async {
    let source = ControlledTTSStreamSource()
    let players = FakeProgressivePlayerStore()
    var fallbackCount = 0
    let pipeline = makePipeline(source: source, players: players)
    pipeline.onFallback = { _, _, completion in
      fallbackCount += 1
      completion()
    }

    pipeline.enqueue("cancel me")
    await source.waitUntilRequested("cancel me")
    await source.yield(Data([1]), to: "cancel me")
    await waitUntil { players.created.first?.didStart == true }
    pipeline.cancel()
    await source.waitUntilTerminated("cancel me")

    XCTAssertTrue(players.created[0].didStop)
    XCTAssertEqual(fallbackCount, 0)
    XCTAssertFalse(pipeline.isActive)
  }

  func testStallTimeoutCancelsStreamAndUsesWholeTextFallback() async {
    let source = ControlledTTSStreamSource()
    let players = FakeProgressivePlayerStore()
    let stall = ControlledStallWaiter()
    let fallback = expectation(description: "stall fallback")
    var fallbackText: String?
    var fallbackError: Error?
    let pipeline = makePipeline(
      source: source,
      players: players,
      stallWaiter: { try await stall.wait() })
    pipeline.onFallback = { text, error, completion in
      fallbackText = text
      fallbackError = error
      completion()
      fallback.fulfill()
    }

    pipeline.enqueue("stalling chunk")
    await source.waitUntilRequested("stalling chunk")
    await stall.fire()
    await fulfillment(of: [fallback], timeout: 1)
    await source.waitUntilTerminated("stalling chunk")

    XCTAssertEqual(fallbackText, "stalling chunk")
    XCTAssertEqual(fallbackError as? ProgressiveTTSPlaybackError, .stalled)
    XCTAssertFalse(pipeline.isActive)
  }

  func testNextChunkPrefetchesButCannotPlayBeforeCurrentChunkDrains() async {
    let source = ControlledTTSStreamSource()
    let players = FakeProgressivePlayerStore()
    var started: [String] = []
    let pipeline = makePipeline(source: source, players: players)
    pipeline.onPlaybackStarted = { started.append($0) }

    pipeline.enqueue("one")
    pipeline.enqueue("two")
    await source.waitUntilRequested("one")
    await source.yield(Data([1]), to: "one")
    await waitUntil { started == ["one"] }
    await source.finish("one")

    await source.waitUntilRequested("two")
    await source.yield(Data([2]), to: "two")
    await source.finish("two")
    await Task.yield()

    XCTAssertEqual(started, ["one"])
    XCTAssertEqual(players.created.count, 1, "prefetched bytes must remain inert behind the current chunk")

    players.created[0].drain()
    await waitUntil { started == ["one", "two"] }
    XCTAssertEqual(players.created.count, 2)
    await waitUntil { players.created[1].didFinishInput }
    players.created[1].drain()
    await waitUntil { !pipeline.isActive }
  }

  func testPrefetchIsBoundedToOneSuccessor() async {
    let source = ControlledTTSStreamSource()
    let players = FakeProgressivePlayerStore()
    let pipeline = makePipeline(source: source, players: players)

    pipeline.enqueue("one")
    pipeline.enqueue("two")
    pipeline.enqueue("three")
    await source.waitUntilRequested("one")
    await source.yield(Data([1]), to: "one")
    await source.finish("one")
    await source.waitUntilRequested("two")
    await source.yield(Data([2]), to: "two")
    await source.finish("two")
    await Task.yield()

    let requestedThirdEarly = await source.hasRequest("three")
    XCTAssertFalse(requestedThirdEarly, "only one successor may prefetch behind active playback")

    players.created[0].drain()
    await source.waitUntilRequested("three")
    await source.yield(Data([3]), to: "three")
    await source.finish("three")
    await waitUntil { players.created.count == 2 }
    players.created[1].drain()
    await waitUntil { players.created.count == 3 }
    await waitUntil { players.created[2].didFinishInput }
    players.created[2].drain()
    await waitUntil { !pipeline.isActive }
  }

  private func makePipeline(
    source: ControlledTTSStreamSource,
    players: FakeProgressivePlayerStore,
    stallWaiter: ProgressiveTTSPlaybackPipeline.StallWaiter? = nil
  ) -> ProgressiveTTSPlaybackPipeline {
    let suspendedWaiter = ControlledStallWaiter()
    let resolvedStallWaiter: ProgressiveTTSPlaybackPipeline.StallWaiter =
      stallWaiter ?? { try await suspendedWaiter.wait() }
    return ProgressiveTTSPlaybackPipeline(
      streamFactory: { text in await source.stream(for: text) },
      playerFactory: { players.makePlayer() },
      stallWaiter: resolvedStallWaiter)
  }

  private func waitUntil(
    _ condition: @escaping @MainActor () -> Bool,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async {
    for _ in 0..<1_000 {
      if condition() { return }
      await Task.yield()
    }
    XCTFail("Condition did not become true", file: file, line: line)
  }
}

private enum TestStreamError: Error {
  case disconnected
}

private actor ControlledTTSStreamSource {
  private struct Entry {
    let continuation: AsyncThrowingStream<Data, Error>.Continuation
    var isFinished = false
    var isTerminated = false
  }

  private var entries: [String: Entry] = [:]
  private var requestWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]
  private var terminationWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]

  func stream(for text: String) -> AsyncThrowingStream<Data, Error> {
    let pair = AsyncThrowingStream<Data, Error>.makeStream()
    pair.continuation.onTermination = { [weak self] _ in
      Task { await self?.markTerminated(text) }
    }
    entries[text] = Entry(continuation: pair.continuation)
    for waiter in requestWaiters.removeValue(forKey: text) ?? [] { waiter.resume() }
    return pair.stream
  }

  func waitUntilRequested(_ text: String) async {
    if entries[text] != nil { return }
    await withCheckedContinuation { continuation in
      requestWaiters[text, default: []].append(continuation)
    }
  }

  func yield(_ data: Data, to text: String) {
    entries[text]?.continuation.yield(data)
  }

  func finish(_ text: String) {
    guard var entry = entries[text] else { return }
    entry.isFinished = true
    entries[text] = entry
    entry.continuation.finish()
  }

  func fail(_ error: Error, text: String) {
    guard var entry = entries[text] else { return }
    entry.isFinished = true
    entries[text] = entry
    entry.continuation.finish(throwing: error)
  }

  func isFinished(_ text: String) -> Bool {
    entries[text]?.isFinished == true
  }

  func hasRequest(_ text: String) -> Bool {
    entries[text] != nil
  }

  func waitUntilTerminated(_ text: String) async {
    if entries[text]?.isTerminated == true { return }
    await withCheckedContinuation { continuation in
      terminationWaiters[text, default: []].append(continuation)
    }
  }

  private func markTerminated(_ text: String) {
    if var entry = entries[text] {
      entry.isTerminated = true
      entries[text] = entry
    }
    for waiter in terminationWaiters.removeValue(forKey: text) ?? [] { waiter.resume() }
  }
}

private actor ControlledStallWaiter {
  private var continuations: [AsyncStream<Void>.Continuation] = []

  func wait() async throws {
    let pair = AsyncStream<Void>.makeStream()
    continuations.append(pair.continuation)
    for await _ in pair.stream { return }
    throw CancellationError()
  }

  func fire() {
    let pending = continuations
    continuations.removeAll()
    for continuation in pending {
      continuation.yield(())
      continuation.finish()
    }
  }
}

@MainActor
private final class FakeProgressivePlayerStore {
  private(set) var created: [FakeProgressivePlayer] = []

  func makePlayer() -> FakeProgressivePlayer {
    let player = FakeProgressivePlayer()
    created.append(player)
    return player
  }
}

@MainActor
private final class FakeProgressivePlayer: ProgressiveAudioPlaying {
  var onStarted: (() -> Void)?
  var onDrained: ((TimeInterval) -> Void)?
  private(set) var didStart = false
  private(set) var didFinishInput = false
  private(set) var didStop = false

  func append(_ data: Data) throws {
    guard !data.isEmpty, !didStop else { return }
    if !didStart {
      didStart = true
      onStarted?()
    }
  }

  func finish() {
    didFinishInput = true
  }

  func stop() {
    didStop = true
  }

  func drain(playedMediaDuration: TimeInterval = 0) {
    onDrained?(playedMediaDuration)
  }
}
