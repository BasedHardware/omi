import CoreAudio
import XCTest

@testable import Omi_Computer

/// Fault coverage for the CoreAudio routing snapshot behind PTT input selection.
/// `ShortcutSettingsTests` pins the pure selection policy; these tests pin what the
/// main actor sees while the HAL is slow, wedged, or has not answered yet.
final class PTTInputDeviceProbeTests: XCTestCase {
  override func setUp() {
    super.setUp()
    PTTInputDeviceRouting.resetForTests()
  }

  override func tearDown() {
    PTTInputDeviceRouting.resetForTests()
    super.tearDown()
  }

  /// A probe whose device lookup blocks until the test releases it, standing in for a
  /// wedged CoreAudio driver without sleeping on the wall clock.
  private func stalledProbe(until release: DispatchSemaphore) -> PTTAudioDeviceProbe {
    PTTAudioDeviceProbe(
      inputDeviceID: { _ in
        release.wait()
        return 99
      },
      outputIsBluetooth: { true },
      builtInMicDeviceID: { 42 }
    )
  }

  private func probe(
    selected: AudioDeviceID? = nil,
    bluetooth: Bool = false,
    builtIn: AudioDeviceID? = nil
  ) -> PTTAudioDeviceProbe {
    PTTAudioDeviceProbe(
      inputDeviceID: { _ in selected },
      outputIsBluetooth: { bluetooth },
      builtInMicDeviceID: { builtIn }
    )
  }

  /// Refresh and block the *test* until the snapshot lands. Production never does this.
  private func refreshAndWait(selectedUID: String, probe: PTTAudioDeviceProbe) {
    let landed = expectation(description: "routing snapshot landed")
    PTTInputDeviceRouting.refresh(selectedUID: selectedUID, probe: probe) { landed.fulfill() }
    wait(for: [landed], timeout: 5)
  }

  // MARK: - The issue #10442 acceptance criterion

  /// "proving PTT startup and the main run loop remain responsive". A bounded wait on
  /// the main thread does not satisfy this: it still parks the run loop for the whole
  /// budget. The turn-start read must not wait on CoreAudio at all.
  @MainActor
  func testMainRunLoopKeepsPumpingWhileTheHALIsWedged() {
    let release = DispatchSemaphore(value: 0)
    // Joined before returning: a probe still parked at teardown would publish its
    // snapshot into whichever test runs next.
    let finished = expectation(description: "parked probe finished")
    PTTInputDeviceRouting.refresh(
      selectedUID: "wedged-uid", probe: stalledProbe(until: release)
    ) { finished.fulfill() }

    let ticker = Ticker()
    let timer = Timer.scheduledTimer(withTimeInterval: 0.01, repeats: true) { _ in ticker.tick() }
    RunLoop.main.add(timer, forMode: .common)
    defer { timer.invalidate() }

    let started = Date()
    var reads = 0
    while Date().timeIntervalSince(started) < 0.3 {
      // The exact call PTT turn start makes, hammered while the HAL is wedged.
      _ = PTTInputDeviceRouting.currentSnapshot(selectedUID: "wedged-uid")
      reads += 1
      RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01))
    }

    XCTAssertGreaterThan(
      ticker.count, 10,
      "the main run loop must keep pumping while the HAL is wedged (got \(ticker.count) ticks)")
    XCTAssertGreaterThan(reads, 10, "turn-start reads must keep completing")

    release.signal()
    wait(for: [finished], timeout: 5)
  }

  /// A wedged driver must not leak one parked thread per PTT turn.
  func testConcurrentRefreshesCoalesceIntoASingleHALRead() {
    let release = DispatchSemaphore(value: 0)
    let starts = Ticker()
    let counting = PTTAudioDeviceProbe(
      inputDeviceID: { _ in
        starts.tick()
        release.wait()
        return 99
      },
      outputIsBluetooth: { true },
      builtInMicDeviceID: { 42 }
    )

    let finished = expectation(description: "every refresh call settled")
    finished.expectedFulfillmentCount = 25
    for _ in 0..<25 {
      PTTInputDeviceRouting.refresh(selectedUID: "wedged-uid", probe: counting) {
        finished.fulfill()
      }
    }
    // Give the queue a chance to start anything it was going to start.
    let settled = expectation(description: "settled")
    DispatchQueue.global().asyncAfter(deadline: .now() + 0.2) { settled.fulfill() }
    wait(for: [settled], timeout: 5)

    XCTAssertEqual(
      starts.count, 1,
      "25 turn starts against a wedged driver must park exactly one probe thread")

    release.signal()
    wait(for: [finished], timeout: 5)
  }

  // MARK: - Policy preservation

  func testResolvedSnapshotKeepsTheExplicitUserChoice() {
    refreshAndWait(
      selectedUID: "user-mic-uid", probe: probe(selected: 7, bluetooth: true, builtIn: 42))
    XCTAssertEqual(
      PTTInputDeviceRouting.currentSnapshot(selectedUID: "user-mic-uid")?.overrideDeviceID, 7)
  }

  func testResolvedSnapshotFallsBackToBuiltInMicOnBluetoothOutput() {
    refreshAndWait(selectedUID: "", probe: probe(bluetooth: true, builtIn: 42))
    XCTAssertEqual(PTTInputDeviceRouting.currentSnapshot(selectedUID: "")?.overrideDeviceID, 42)
  }

  func testResolvedSnapshotUsesTheSystemDefaultWhenOutputIsNotBluetooth() {
    refreshAndWait(selectedUID: "", probe: probe())
    let snapshot = PTTInputDeviceRouting.currentSnapshot(selectedUID: "")
    XCTAssertNotNil(snapshot, "a resolved snapshot must exist")
    XCTAssertNil(snapshot?.overrideDeviceID)
  }

  func testAnUnpluggedSelectedMicFallsBackToTheBluetoothBuiltInRule() {
    refreshAndWait(
      selectedUID: "unplugged-mic-uid", probe: probe(bluetooth: true, builtIn: 42))
    XCTAssertEqual(
      PTTInputDeviceRouting.currentSnapshot(selectedUID: "unplugged-mic-uid")?.overrideDeviceID,
      42)
  }

  func testTheBuiltInMicIsNotEnumeratedWhenOutputIsNotBluetooth() {
    let builtInReads = Ticker()
    refreshAndWait(
      selectedUID: "",
      probe: PTTAudioDeviceProbe(
        inputDeviceID: { _ in nil },
        outputIsBluetooth: { false },
        builtInMicDeviceID: {
          builtInReads.tick()
          return 42
        }))

    XCTAssertEqual(
      builtInReads.count, 0,
      "the built-in mic lookup is the most expensive HAL walk and is only needed for the "
        + "Bluetooth A2DP fallback")
  }

  // MARK: - Cold and stale snapshots

  func testAColdSnapshotReportsNoOverrideRatherThanGuessing() {
    XCTAssertNil(PTTInputDeviceRouting.currentSnapshot(selectedUID: "user-mic-uid"))
  }

  /// A snapshot resolved for the previous microphone must never be applied after the
  /// user picks a different one.
  func testASnapshotForAnotherMicrophoneIsNotApplied() {
    refreshAndWait(selectedUID: "old-mic-uid", probe: probe(selected: 7))
    XCTAssertEqual(
      PTTInputDeviceRouting.currentSnapshot(selectedUID: "old-mic-uid")?.overrideDeviceID, 7)
    XCTAssertNil(PTTInputDeviceRouting.currentSnapshot(selectedUID: "new-mic-uid"))
  }
}

private final class Ticker: @unchecked Sendable {
  private let lock = NSLock()
  private var value = 0

  func tick() {
    lock.lock()
    defer { lock.unlock() }
    value += 1
  }

  var count: Int {
    lock.lock()
    defer { lock.unlock() }
    return value
  }
}
