import XCTest

@testable import Omi_Computer

@MainActor
final class VoiceTypeOpeningDecoderTests: XCTestCase {
  func testExactOpeningReusesCompletedDecodeButLongerOpeningDoesNot() async {
    let decoder = VoiceTypeOpeningDecoder()
    let probe = DecodeProbe()
    let opening = Data([1, 2])
    let first = await decoder.decode(opening) { await probe.decode($0) }
    let cached = await decoder.decode(opening) { await probe.decode($0) }
    let longer = await decoder.decode(Data([1, 2, 3])) { await probe.decode($0) }
    XCTAssertEqual(first, "question 2")
    XCTAssertEqual(cached, first)
    XCTAssertEqual(longer, "question 3")
    let calls = await probe.calls
    XCTAssertEqual(calls, 2)
  }

  func testNextTurnCannotReusePreviousOpening() async {
    let decoder = VoiceTypeOpeningDecoder()
    let probe = DecodeProbe()
    _ = await decoder.decode(Data([1])) { await probe.decode($0) }
    decoder.reset()
    _ = await decoder.decode(Data([1])) { await probe.decode($0) }
    let calls = await probe.calls
    XCTAssertEqual(calls, 2)
  }

  func testFailedDecodeCanRetrySameAudio() async {
    let decoder = VoiceTypeOpeningDecoder()
    let failed = await decoder.decode(Data([1])) { _ in nil }
    let retried = await decoder.decode(Data([1])) { _ in "type hello" }
    XCTAssertNil(failed)
    XCTAssertEqual(retried, "type hello")
  }

  func testReleaseJoinsAnIdenticalProbeAlreadyInFlight() async {
    let decoder = VoiceTypeOpeningDecoder()
    let gate = DecodeGate()
    let audio = Data([1, 2])
    let first = Task { await decoder.decode(audio) { await gate.decode($0) } }
    await gate.waitUntilStarted()
    let joined = expectation(description: "release entered decoder")
    let second = Task { @MainActor in
      joined.fulfill()
      return await decoder.decode(audio) { await gate.decode($0) }
    }
    await fulfillment(of: [joined])
    await gate.finish("type hello")
    let firstText = await first.value
    let secondText = await second.value
    XCTAssertEqual(firstText, "type hello")
    XCTAssertEqual(secondText, firstText)
    let calls = await gate.calls
    XCTAssertEqual(calls, 1)
  }

  func testResetRejectsLateCompletionEvenWhenDecoderIgnoresCancellation() async {
    let decoder = VoiceTypeOpeningDecoder()
    let gate = DecodeGate()
    let first = Task { await decoder.decode(Data([1])) { await gate.decode($0) } }
    await gate.waitUntilStarted()
    decoder.reset()
    let next = await decoder.decode(Data([1])) { _ in "new question" }
    await gate.finish("old question")
    let stale = await first.value
    XCTAssertEqual(next, "new question")
    XCTAssertNil(stale)
  }

  func testLongerInFlightOpeningFencesShorterDecodeThatCompletesLater() async {
    let decoder = VoiceTypeOpeningDecoder()
    let gate = PrefixDecodeGate()
    let short = Data([1, 2])
    let longer = Data([1, 2, 3])

    let shortTask = Task { await decoder.decode(short) { await gate.decode($0) } }
    await gate.waitUntilStarted(short)
    let longerTask = Task { await decoder.decode(longer) { await gate.decode($0) } }
    await gate.waitUntilStarted(longer)
    await gate.waitUntilCancelled(short)

    // The released audio gets a new decoder entry. Complete it first, then
    // let the cancellation-ignoring shorter probe arrive late.
    await gate.finish(longer, text: "type longer")
    let longerText = await longerTask.value
    await gate.finish(short, text: "type short")
    let shortText = await shortTask.value

    XCTAssertEqual(longerText, "type longer")
    XCTAssertNil(shortText, "a stale shorter prefix must not authorize the released opening")
    let calls = await gate.calls
    XCTAssertEqual(calls, 2)
  }

  private actor DecodeGate {
    var calls = 0
    private var pending: CheckedContinuation<String?, Never>?
    private var started: CheckedContinuation<Void, Never>?

    func decode(_ audio: Data) async -> String? {
      calls += 1
      return await withCheckedContinuation { continuation in
        pending = continuation
        started?.resume()
        started = nil
      }
    }

    func waitUntilStarted() async {
      if pending != nil { return }
      await withCheckedContinuation { started = $0 }
    }

    func finish(_ text: String) {
      pending?.resume(returning: text)
      pending = nil
    }
  }

  private actor PrefixDecodeGate {
    private var pending: [Data: CheckedContinuation<String?, Never>] = [:]
    private var started: Set<Data> = []
    private var cancelled: Set<Data> = []
    private var startWaiters: [Data: [CheckedContinuation<Void, Never>]] = [:]
    private var cancellationWaiters: [Data: [CheckedContinuation<Void, Never>]] = [:]
    private(set) var calls = 0

    func decode(_ audio: Data) async -> String? {
      calls += 1
      started.insert(audio)
      for waiter in startWaiters.removeValue(forKey: audio) ?? [] {
        waiter.resume()
      }
      return await withTaskCancellationHandler {
        await withCheckedContinuation { continuation in
          pending[audio] = continuation
        }
      } onCancel: {
        Task { await self.markCancelled(audio) }
      }
    }

    func waitUntilStarted(_ audio: Data) async {
      if started.contains(audio) { return }
      await withCheckedContinuation { continuation in
        startWaiters[audio, default: []].append(continuation)
      }
    }

    func waitUntilCancelled(_ audio: Data) async {
      if cancelled.contains(audio) { return }
      await withCheckedContinuation { continuation in
        cancellationWaiters[audio, default: []].append(continuation)
      }
    }

    func finish(_ audio: Data, text: String) {
      pending.removeValue(forKey: audio)?.resume(returning: text)
    }

    private func markCancelled(_ audio: Data) {
      cancelled.insert(audio)
      for waiter in cancellationWaiters.removeValue(forKey: audio) ?? [] {
        waiter.resume()
      }
    }
  }

  private actor DecodeProbe {
    var calls = 0
    func decode(_ audio: Data) -> String {
      calls += 1
      return "question \(audio.count)"
    }
  }
}
