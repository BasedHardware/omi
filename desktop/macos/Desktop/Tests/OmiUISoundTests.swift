import Foundation
import XCTest

@testable import Omi_Computer

/// Records what the app-wide cue layer asked CoreAudio for, without CoreAudio. `@unchecked
/// Sendable` with a lock, because `OmiSoundOutput` is `Sendable` so the real implementation can
/// hand work to its own queue.
private final class RecordingSoundOutput: OmiSoundOutput, @unchecked Sendable {
  private let lock = NSLock()
  private var storage: [OmiSoundAsset] = []

  var oneShots: [OmiSoundAsset] {
    lock.lock()
    defer { lock.unlock() }
    return storage
  }

  func preload(_ assets: [OmiSoundAsset: URL]) {}
  func startLoop(_ asset: OmiSoundAsset, fadeIn: TimeInterval) {}
  func stopLoop(fadeOut: TimeInterval) {}
  func playOneShot(_ asset: OmiSoundAsset) {
    lock.lock()
    storage.append(asset)
    lock.unlock()
  }
}

/// A clock the test moves by hand, so the coalescing window is asserted without waiting for it.
private final class ManualClock: @unchecked Sendable {
  private let lock = NSLock()
  private var seconds: TimeInterval = 1_000

  var now: TimeInterval {
    lock.lock()
    defer { lock.unlock() }
    return seconds
  }

  func advance(by interval: TimeInterval) {
    lock.lock()
    seconds += interval
    lock.unlock()
  }
}

/// The class itself is nonisolated so `setUpWithError`/`tearDownWithError` stay on the hooks' own
/// isolation; only the tests that touch the main-actor types hop.
final class OmiUISoundTests: XCTestCase {
  // XCTest builds a fresh instance per test method, so initializing at the declaration gives each
  // test its own scratch directory and defaults suite without a mutable, implicitly-unwrapped
  // property that every test body would then have to trust was set.
  private let scratch = FileManager.default.temporaryDirectory
    .appendingPathComponent("omi-ui-sound-\(UUID().uuidString)", isDirectory: true)
  private var soundsDirectory: URL { scratch.appendingPathComponent("Sounds", isDirectory: true) }
  private let defaultsSuite = "omi.uisound.tests.\(UUID().uuidString)"

  /// `UserDefaults(suiteName:)` is failable, and the tempting `?? .standard` would quietly write
  /// this suite's test state into the real defaults domain. Fail the test instead.
  private lazy var defaults: UserDefaults = {
    guard let suite = UserDefaults(suiteName: defaultsSuite) else {
      XCTFail("could not create UserDefaults suite \(defaultsSuite)")
      return .standard
    }
    return suite
  }()

  override func setUpWithError() throws {
    try super.setUpWithError()
    try FileManager.default.createDirectory(at: soundsDirectory, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: scratch)
    UserDefaults.standard.removePersistentDomain(forName: defaultsSuite)
    try super.tearDownWithError()
  }

  private func writeAllAssets() throws {
    for asset in OmiSoundAsset.allCases {
      try Data().write(to: soundsDirectory.appendingPathComponent(asset.fileName))
    }
  }

  @MainActor
  private func makeController(
    output: RecordingSoundOutput,
    systemUISoundsEnabled: @escaping () -> Bool = { true }
  ) -> OmiSoundController {
    OmiSoundController(
      output: output,
      locator: OmiSoundAssetLocator(roots: [soundsDirectory]),
      systemUISoundsEnabled: systemUISoundsEnabled,
      defaults: defaults)
  }

  @MainActor
  private func makeService(
    output: RecordingSoundOutput,
    systemUISoundsEnabled: @escaping () -> Bool = { true },
    reduceMotion: @escaping () -> Bool = { false },
    clock: ManualClock = ManualClock()
  ) -> OmiUISoundService {
    OmiUISoundService(
      controller: makeController(output: output, systemUISoundsEnabled: systemUISoundsEnabled),
      reduceMotionEnabled: reduceMotion,
      now: { clock.now })
  }

  // MARK: - The palette

  @MainActor
  func testEveryCueMapsToAOneShotAndOnlyMovementCuesAreMotionTied() {
    // `pad` is the bed and has no cue: firing a 24-second loop as a one-shot is the mistake the
    // separate `OmiSoundEffect` type exists to make unrepresentable.
    for cue in OmiUICue.allCases {
      XCTAssertNotEqual(cue.effect.asset, .pad, "\(cue.rawValue) must not fire the ambient bed")
    }
    XCTAssertEqual(OmiUICue.allCases.filter(\.voicesMotion), [.reveal])
    XCTAssertEqual(OmiUICue.reveal.effect, .swoosh)
    XCTAssertEqual(OmiUICue.complete.effect, .chime)
  }

  @MainActor
  func testAppWidePaletteContainsOnlyArrivalAndCompletionSounds() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let service = makeService(output: output)

    for cue in OmiUICue.allCases { service.play(cue) }

    XCTAssertEqual(OmiUICue.allCases, [.reveal, .complete])
    XCTAssertEqual(output.oneShots, [.swoosh, .chime])
    XCTAssertFalse(output.oneShots.contains(.click))
  }

  // MARK: - Chrome versus content

  /// The system's "Play user interface sound effects" switch governs chrome. `AVAudioEngine` never
  /// consults it, so the gate is applied here — and completion cues are content, which the switch
  /// has no say over.
  @MainActor
  func testTheSystemUISwitchSilencesChromeCuesAndLeavesCompletionAlone() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let service = makeService(output: output, systemUISoundsEnabled: { false })

    for cue in OmiUICue.allCases {
      XCTAssertEqual(
        service.allows(cue), cue == .complete,
        "\(cue.rawValue) is \(cue == .complete ? "content" : "chrome")")
      service.play(cue)
    }

    XCTAssertEqual(output.oneShots, [.chime])
  }

  @MainActor
  func testEveryCueIsHeardWhenTheSystemSwitchIsOn() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let service = makeService(output: output, systemUISoundsEnabled: { true })

    for cue in OmiUICue.allCases { service.play(cue) }

    XCTAssertEqual(Set(output.oneShots), [.swoosh, .chime])
  }

  // MARK: - The app's own mute

  @MainActor
  func testTheMuteSilencesContentAsWellAsChromeAndSurvivesARestart() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let service = makeService(output: output)

    XCTAssertTrue(service.isEnabled, "an install that has never seen the control still gets sound")
    service.isEnabled = false

    for cue in OmiUICue.allCases {
      XCTAssertFalse(service.allows(cue))
      service.play(cue)
    }
    XCTAssertEqual(output.oneShots, [], "a muted app must not reach the audio graph at all")
    XCTAssertEqual(
      defaults.object(forKey: OmiSoundController.effectsEnabledDefaultsKey) as? Bool, false)

    // A fresh service over the same defaults comes back muted.
    let restartedOutput = RecordingSoundOutput()
    let restarted = makeService(output: restartedOutput)
    XCTAssertFalse(restarted.isEnabled)
    restarted.play(.complete)
    XCTAssertEqual(restartedOutput.oneShots, [])

    restarted.isEnabled = true
    restarted.play(.complete)
    XCTAssertEqual(restartedOutput.oneShots, [.chime])
  }

  /// The mute is the controller's, not this layer's, so cues fired straight through the controller
  /// — onboarding's — honour it too. One switch, or the switch is a lie.
  @MainActor
  func testTheMuteAlsoSilencesCuesFiredDirectlyThroughTheController() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let controller = makeController(output: output)
    let service = OmiUISoundService(controller: controller, reduceMotionEnabled: { false })

    service.isEnabled = false
    controller.play(.click)
    controller.play(.chime)

    XCTAssertEqual(output.oneShots, [])
  }

  // MARK: - Reduce Motion

  @MainActor
  func testReduceMotionSilencesOnlyTheCueThatVoicesMovement() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let service = makeService(output: output, reduceMotion: { true })

    XCTAssertFalse(service.allows(.reveal))
    for cue in OmiUICue.allCases { service.play(cue) }

    XCTAssertFalse(output.oneShots.contains(.swoosh), "nothing moved, so nothing narrates a move")
    XCTAssertEqual(output.oneShots, [.chime])
  }

  // MARK: - No cue storms

  @MainActor
  func testTheSameCueTwiceInsideTheWindowIsHeardOnce() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let clock = ManualClock()
    let service = makeService(output: output, clock: clock)

    // A completion handler re-entered inside one frame.
    service.play(.complete)
    clock.advance(by: OmiUISoundService.coalescingWindow / 2)
    service.play(.complete)
    XCTAssertEqual(output.oneShots, [.chime])

    // A different cue in the same breath is a different event and still lands.
    service.play(.reveal)
    XCTAssertEqual(output.oneShots, [.chime, .swoosh])

    // Past the window, the user has genuinely acted again.
    clock.advance(by: OmiUISoundService.coalescingWindow)
    service.play(.complete)
    XCTAssertEqual(output.oneShots, [.chime, .swoosh, .chime])
  }

  @MainActor
  func testASuppressedCueDoesNotConsumeTheWindow() throws {
    try writeAllAssets()
    let output = RecordingSoundOutput()
    let clock = ManualClock()
    let service = makeService(output: output, reduceMotion: { true }, clock: clock)

    // Reduce Motion is off after the first attempt; the swoosh that never played must not be what
    // stops the next one.
    service.play(.reveal)
    let heard = makeService(output: output, reduceMotion: { false }, clock: clock)
    heard.play(.reveal)

    XCTAssertEqual(output.oneShots, [.swoosh])
  }

  // MARK: - Degrading to silence

  /// Nothing on disk is the shape a broken install takes. Every cue must be a no-op, not a throw
  /// and not a crash — a status cue is never allowed to be the thing that breaks.
  @MainActor
  func testCuesAreSilentAndHarmlessWhenNoAssetLoads() {
    let output = RecordingSoundOutput()
    let service = makeService(output: output)

    for cue in OmiUICue.allCases {
      // The gate says yes — policy is fine; it is the asset that is missing.
      XCTAssertTrue(service.allows(cue))
      service.play(cue)
    }

    XCTAssertEqual(output.oneShots, [])
  }

  @MainActor
  func testAMissingAssetSilencesOnlyTheCuesThatNeedIt() throws {
    try Data().write(to: soundsDirectory.appendingPathComponent(OmiSoundAsset.chime.fileName))
    let output = RecordingSoundOutput()
    let service = makeService(output: output)

    for cue in OmiUICue.allCases { service.play(cue) }

    XCTAssertEqual(output.oneShots, [.chime])
  }
}
