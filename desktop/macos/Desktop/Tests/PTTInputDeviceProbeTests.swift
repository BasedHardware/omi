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
  private func stalledProbe(
    until release: DispatchSemaphore,
    onStart: (@Sendable () -> Void)? = nil
  ) -> PTTAudioDeviceProbe {
    PTTAudioDeviceProbe(
      inputDeviceID: { _ in
        onStart?()
        release.wait()
        return 99
      },
      outputIsBluetooth: { true },
      builtInMicDeviceID: { 42 },
      defaultInputDeviceID: { nil },
      isBluetoothInput: { _ in false }
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
      builtInMicDeviceID: { builtIn },
      defaultInputDeviceID: { nil },
      isBluetoothInput: { _ in false }
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
  func testMainRunLoopKeepsPumpingWhileTheHALIsWedged() async {
    let release = DispatchSemaphore(value: 0)
    let started = expectation(description: "HAL probe started")
    // Joined before returning: a probe still parked at teardown would publish its
    // snapshot into whichever test runs next.
    let finished = expectation(description: "parked probe finished")
    PTTInputDeviceRouting.refresh(
      selectedUID: "wedged-uid",
      probe: stalledProbe(until: release) { started.fulfill() }
    ) { finished.fulfill() }
    await fulfillment(of: [started], timeout: 5)

    let mainActorProgress = expectation(description: "main actor kept making progress")
    mainActorProgress.expectedFulfillmentCount = 3
    let snapshotReads = expectation(description: "turn-start snapshot reads completed")
    snapshotReads.expectedFulfillmentCount = 3
    for _ in 0..<3 {
      DispatchQueue.main.async {
        mainActorProgress.fulfill()
      }
      DispatchQueue.global().async {
        // Exercise the exact turn-start read off-main so a regression times out
        // without blocking the main actor that must release the wedged probe.
        XCTAssertNil(PTTInputDeviceRouting.currentSnapshot(selectedUID: "wedged-uid"))
        snapshotReads.fulfill()
      }
    }
<<<<<<< HEAD
    await fulfillment(of: [mainActorProgress, snapshotReads], timeout: 5)
=======

    // A responsive run loop pumps this 10ms ticker many times over 0.3s (~30 on a fast
    // machine); a run loop wedged by a blocking `currentSnapshot` pumps ~0. The assertion only
    // needs to separate those two regimes, so the threshold is deliberately low: a slow or
    // loaded CI runner (observed as few as 5 ticks) must never flake, while a genuinely wedged
    // loop (~0 ticks) still fails loudly. Do not raise this to chase a fast-machine number.
    XCTAssertGreaterThan(
      ticker.count, 2,
      "the main run loop must keep pumping while the HAL is wedged (got \(ticker.count) ticks)")
    XCTAssertGreaterThan(reads, 2, "turn-start reads must keep completing")
>>>>>>> 402765359b (test(desktop): make PTT run-loop probe tolerant of slow CI runners)

    release.signal()
    await fulfillment(of: [finished], timeout: 5)
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
      builtInMicDeviceID: { 42 },
      defaultInputDeviceID: { nil },
      isBluetoothInput: { _ in false }
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
        },
        defaultInputDeviceID: { nil },
        isBluetoothInput: { _ in false }))

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
