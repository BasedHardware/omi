import XCTest

@testable import Omi_Computer

/// Regression coverage for a Stop/disconnect that lands while `startProcessing`
/// is awaiting the device's `getAudioCodec()` BLE read.
///
/// `startProcessing` claims the slot (`isProcessing = true`) synchronously, then
/// suspends on `getAudioCodec()`. For Omi/OpenGlass that await is a real BLE
/// characteristic read. A quick Stop during that window runs `stopProcessing()`
/// on the main actor — clearing `isProcessing` and dropping the handlers. Before
/// the generation fence, the resumed start re-armed `isProcessing` and created a
/// processor with the handlers already nil, leaving a wedged session. The start
/// must now detect it was superseded and abort.
@MainActor
final class BleAudioServiceStartStopRaceTests: XCTestCase {
  override func tearDown() async throws {
    BleAudioService.shared.stopProcessing()
    try await super.tearDown()
  }

  func testStopDuringCodecReadAbortsResumedStart() async {
    BleAudioService.shared.stopProcessing()

    let entered = TestAsyncGate()
    let release = TestAsyncGate()
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice, sessionGeneration: 1)
    connection.audioCodecEnteredGate = entered
    connection.audioCodecReleaseGate = release

    let start = Task { await BleAudioService.shared.startProcessing(from: connection) }

    // The start has claimed the slot and is now suspended inside getAudioCodec().
    await entered.wait()
    XCTAssertTrue(BleAudioService.shared.isProcessing, "slot is claimed before the codec await returns")

    // User presses Stop (or the device disconnects) during the codec read.
    BleAudioService.shared.stopProcessing()
    XCTAssertFalse(BleAudioService.shared.isProcessing, "Stop clears the processing slot")

    // Let the codec read return; the resumed start must NOT re-arm processing.
    await release.open()
    await start.value

    XCTAssertFalse(
      BleAudioService.shared.isProcessing,
      "a start superseded by Stop during the codec await must not re-arm processing")
  }
}
