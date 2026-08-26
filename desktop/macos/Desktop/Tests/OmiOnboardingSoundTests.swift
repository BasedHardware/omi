import Foundation
import XCTest

@testable import Omi_Computer

/// Everything CoreAudio was asked to do, without CoreAudio. `@unchecked Sendable` with a lock,
/// because `OmiSoundOutput` is `Sendable` so the real implementation can hand work to its own
/// queue.
private final class FakeSoundOutput: OmiSoundOutput, @unchecked Sendable {
  enum Event: Equatable {
    case preload([OmiSoundAsset])
    case startLoop(OmiSoundAsset, TimeInterval)
    case stopLoop(TimeInterval)
    case oneShot(OmiSoundAsset)
  }

  private let lock = NSLock()
  private var storage: [Event] = []

  var events: [Event] {
    lock.lock()
    defer { lock.unlock() }
    return storage
  }

  private func record(_ event: Event) {
    lock.lock()
    storage.append(event)
    lock.unlock()
  }

  func preload(_ assets: [OmiSoundAsset: URL]) {
    record(.preload(assets.keys.sorted { $0.rawValue < $1.rawValue }))
  }
  func startLoop(_ asset: OmiSoundAsset, fadeIn: TimeInterval) { record(.startLoop(asset, fadeIn)) }
  func stopLoop(fadeOut: TimeInterval) { record(.stopLoop(fadeOut)) }
  func playOneShot(_ asset: OmiSoundAsset) { record(.oneShot(asset)) }
}

/// The class itself is nonisolated so `setUpWithError`/`tearDownWithError` stay on the hooks'
/// own (nonisolated) isolation; only the tests that touch the main-actor `OmiSoundController` hop.
final class OmiOnboardingSoundTests: XCTestCase {
  // XCTest builds a fresh instance per test method, so initializing at the declaration gives each
  // test its own scratch directory and defaults suite without a mutable, implicitly-unwrapped
  // property that every test body would then have to trust was set.
  private let scratch = FileManager.default.temporaryDirectory
    .appendingPathComponent("omi-cinematic-sound-\(UUID().uuidString)", isDirectory: true)
  private var soundsDirectory: URL { scratch.appendingPathComponent("Sounds", isDirectory: true) }
  private let defaultsSuite = "omi.cinematic.tests.\(UUID().uuidString)"

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

  /// Every asset present, so the controller's own policy is the only thing under test.
  private func writeAllAssets() throws {
    for asset in OmiSoundAsset.allCases {
      try Data().write(to: soundsDirectory.appendingPathComponent(asset.fileName))
    }
  }

  @MainActor
  private func makeController(
    output: FakeSoundOutput,
    systemUISoundsEnabled: @escaping () -> Bool = { true },
    scheduleCap: @escaping (TimeInterval, @escaping @Sendable () -> Void) -> Void = { _, _ in }
  ) -> OmiSoundController {
    OmiSoundController(
      output: output,
      locator: OmiSoundAssetLocator(roots: [soundsDirectory]),
      systemUISoundsEnabled: systemUISoundsEnabled,
      defaults: defaults,
      scheduleCap: scheduleCap)
  }

  // MARK: - Finding the files

  @MainActor
  func testLocatorTakesTheFirstReadableRootAndReportsAMissingAsset() throws {
    try Data().write(to: soundsDirectory.appendingPathComponent(OmiSoundAsset.click.fileName))
    // The flat root is searched too, because `.process("Resources")` may or may not preserve the
    // `Sounds/` subdirectory in the built bundle.
    try Data().write(to: scratch.appendingPathComponent(OmiSoundAsset.chime.fileName))

    let locator = OmiSoundAssetLocator(roots: [soundsDirectory, scratch])
    XCTAssertEqual(
      locator.url(for: .click), soundsDirectory.appendingPathComponent("click.m4a"))
    XCTAssertEqual(locator.url(for: .chime), scratch.appendingPathComponent("chime.m4a"))
    XCTAssertNil(locator.url(for: .pad))
  }

  @MainActor
  func testTheBundledLocatorNeverTrapsWhenNothingIsThere() {
    // `Bundle.resourceBundle` fatalErrors when the lookup fails; a missing sound must cost silence,
    // not the launch, so the bundled roots are computed defensively.
    XCTAssertFalse(OmiSoundAssetLocator.bundledRoots().isEmpty)
  }

  @MainActor
  func testEveryAssetHasItsOwnFileName() {
    let names = Set(OmiSoundAsset.allCases.map(\.fileName))
    XCTAssertEqual(names.count, OmiSoundAsset.allCases.count)
    XCTAssertTrue(names.allSatisfy { $0.hasSuffix(".m4a") })
  }

  // MARK: - The shipped assets

  /// The one thing the rest of this suite fakes away: that the four generated files are actually
  /// committed, actually bundled as resources, and actually decodable into the buffer playback
  /// schedules. `scripts/make-onboarding-sounds.py` regenerates them; this is what proves the
  /// output of that script is what ships.
  @MainActor
  func testTheShippedAssetsAreBundledAndDecodeToTheCanonicalPlaybackFormat() throws {
    // SwiftPM puts the executable target's resource bundle beside the test bundle.
    let buildDirectory = Bundle(for: OmiOnboardingSoundTests.self).bundleURL.deletingLastPathComponent()
    let siblings = try FileManager.default.contentsOfDirectory(
      at: buildDirectory, includingPropertiesForKeys: nil)
    var roots: [URL] = []
    for bundle in siblings where bundle.pathExtension == "bundle" {
      roots.append(bundle)
      roots.append(bundle.appendingPathComponent("Sounds", isDirectory: true))
      roots.append(bundle.appendingPathComponent("Contents/Resources", isDirectory: true))
      roots.append(bundle.appendingPathComponent("Contents/Resources/Sounds", isDirectory: true))
    }
    let locator = OmiSoundAssetLocator(roots: roots)
    let format = try XCTUnwrap(OmiAVSoundOutput.canonicalFormat)

    for asset in OmiSoundAsset.allCases {
      let url = try XCTUnwrap(
        locator.url(for: asset), "\(asset.fileName) is not in any bundled resource directory")
      let buffer = try XCTUnwrap(
        OmiAVSoundOutput.decode(url, to: format), "\(asset.fileName) did not decode")
      XCTAssertEqual(buffer.format.sampleRate, 48_000)
      XCTAssertEqual(buffer.format.channelCount, 2, "every cue is converted to the canonical stereo")
      XCTAssertGreaterThan(buffer.frameLength, 0)
    }

    // The bed is the long one — it is the loop, not a cue.
    let padURL = try XCTUnwrap(locator.url(for: .pad))
    let pad = try XCTUnwrap(OmiAVSoundOutput.decode(padURL, to: format))
    XCTAssertEqual(Double(pad.frameLength) / format.sampleRate, 24, accuracy: 0.05)
  }

  // MARK: - Degrading to silence

  @MainActor
  func testAMissingAssetSilencesOnlyItsOwnCue() throws {
    try Data().write(to: soundsDirectory.appendingPathComponent(OmiSoundAsset.click.fileName))
    let output = FakeSoundOutput()
    let controller = makeController(output: output)

    controller.prepare()
    XCTAssertEqual(controller.availableAssets, [.click])

    controller.play(.click)
    controller.play(.swoosh)
    controller.startMusic(fadeIn: 0)

    XCTAssertEqual(output.events, [.preload([.click]), .oneShot(.click)])
    XCTAssertFalse(controller.isMusicPlaying, "no bed on disk means no bed, not a crash")
  }

  @MainActor
  func testPreparingIsIdempotent() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output)

    controller.prepare()
    controller.prepare()
    controller.play(.click)

    XCTAssertEqual(output.events.filter { if case .preload = $0 { return true } else { return false } }.count, 1)
  }

  // MARK: - The system UI-sound setting

  /// `AVAudioEngine` does not consult "Play user interface sound effects", so the gate is applied
  /// here — and only to chrome. The bed is content and answers to its own control.
  @MainActor
  func testChromeHonoursTheSystemSettingAndContentDoesNot() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output, systemUISoundsEnabled: { false })

    XCTAssertFalse(controller.allows(.click))
    XCTAssertFalse(controller.allows(.swoosh))
    XCTAssertTrue(controller.allows(.chime))

    controller.play(.click)
    controller.play(.swoosh)
    controller.play(.chime)
    controller.startMusic(fadeIn: 0)

    XCTAssertEqual(
      output.events,
      [
        .preload(OmiSoundAsset.allCases.sorted { $0.rawValue < $1.rawValue }),
        .oneShot(.chime),
        .startLoop(.pad, 0),
      ])
    XCTAssertTrue(controller.isMusicPlaying, "the bed is content; the UI-sound switch is not its control")
  }

  @MainActor
  func testChromePlaysWhenTheSystemSettingIsOn() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output, systemUISoundsEnabled: { true })

    controller.play(.click)
    XCTAssertTrue(output.events.contains(.oneShot(.click)))
  }

  // MARK: - The bed

  @MainActor
  func testTheBedStartsOnceAndAlwaysLeavesOnAFade() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output)

    controller.startMusic(fadeIn: OmiOnboardingMusic.defaultFadeIn)
    controller.startMusic(fadeIn: OmiOnboardingMusic.defaultFadeIn)
    XCTAssertTrue(controller.isMusicPlaying)

    controller.stopMusic(fadeOut: OmiOnboardingMusic.defaultFadeOut)
    controller.stopMusic(fadeOut: OmiOnboardingMusic.defaultFadeOut)
    XCTAssertFalse(controller.isMusicPlaying)

    XCTAssertEqual(
      output.events.filter { if case .startLoop = $0 { return true } else { return false } },
      [.startLoop(.pad, OmiOnboardingMusic.defaultFadeIn)])
    XCTAssertEqual(
      output.events.filter { if case .stopLoop = $0 { return true } else { return false } },
      [.stopLoop(OmiOnboardingMusic.defaultFadeOut)])
    XCTAssertLessThan(
      OmiOnboardingMusic.defaultFadeOut, OmiOnboardingMusic.defaultFadeIn,
      "leaving should feel decided; arriving should not")
  }

  @MainActor
  func testANegativeFadeIsClampedRatherThanPassedThrough() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output)

    controller.startMusic(fadeIn: -3)
    controller.stopMusic(fadeOut: -3)

    XCTAssertTrue(output.events.contains(.startLoop(.pad, 0)))
    XCTAssertTrue(output.events.contains(.stopLoop(0)))
  }

  /// Muting is the bed's own control, it fades rather than cuts, and it persists — a user who mutes
  /// the music means it.
  @MainActor
  func testMutingFadesTheBedOutAndSurvivesARestart() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output)

    controller.startMusic(fadeIn: 0)
    XCTAssertTrue(controller.isMusicPlaying)

    controller.isMusicEnabled = false
    XCTAssertFalse(controller.isMusicPlaying)
    XCTAssertTrue(output.events.contains(.stopLoop(OmiOnboardingMusic.defaultFadeOut)))
    XCTAssertEqual(defaults.object(forKey: OmiSoundController.musicEnabledDefaultsKey) as? Bool, false)

    // A fresh controller over the same defaults comes back muted and refuses to start.
    let restartedOutput = FakeSoundOutput()
    let restarted = makeController(output: restartedOutput)
    XCTAssertFalse(restarted.isMusicEnabled)
    restarted.startMusic(fadeIn: 0)
    XCTAssertFalse(restarted.isMusicPlaying)
    XCTAssertFalse(
      restartedOutput.events.contains(.startLoop(.pad, 0)),
      "a muted bed must not reach the audio graph at all")
  }

  @MainActor
  func testAnInstallThatHasNeverSeenTheControlStillGetsTheBed() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output)

    XCTAssertNil(defaults.object(forKey: OmiSoundController.musicEnabledDefaultsKey))
    XCTAssertTrue(controller.isMusicEnabled)

    controller.startMusic(fadeIn: 0)
    XCTAssertTrue(controller.isMusicPlaying)
  }

  @MainActor
  func testUnmutingDoesNotByItselfRestartTheBed() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    let controller = makeController(output: output)

    controller.isMusicEnabled = false
    controller.isMusicEnabled = true

    XCTAssertFalse(controller.isMusicPlaying)
    XCTAssertFalse(output.events.contains(.startLoop(.pad, 0)))
    XCTAssertEqual(defaults.object(forKey: OmiSoundController.musicEnabledDefaultsKey) as? Bool, true)
  }

  // MARK: - The bed is capped

  /// The regression: the bed loops from one buffer with `.loops`, so nothing in the
  /// cinematic ever stopped it and it played for the life of the process.
  @MainActor
  func testMusicFadesItselfOutWhenTheCapFires() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    var fire: (() -> Void)?
    var scheduledDelay: TimeInterval?
    let controller = makeController(
      output: output,
      scheduleCap: { delay, body in
        scheduledDelay = delay
        fire = body
      })

    controller.startMusic(fadeIn: 0)
    XCTAssertTrue(controller.isMusicPlaying)
    XCTAssertEqual(scheduledDelay, OmiSoundController.maxMusicDuration)
    XCTAssertFalse(
      output.events.contains(.stopLoop(OmiOnboardingMusic.defaultFadeOut)),
      "the bed must not be cut before its allowance is spent")

    fire?()

    XCTAssertFalse(controller.isMusicPlaying)
    XCTAssertTrue(output.events.contains(.stopLoop(OmiOnboardingMusic.defaultFadeOut)))
  }

  /// A cap left over from an earlier run must not cut a bed someone started since.
  @MainActor
  func testAStaleCapDoesNotStopALaterBed() throws {
    try writeAllAssets()
    let output = FakeSoundOutput()
    var pending: [() -> Void] = []
    let controller = makeController(
      output: output, scheduleCap: { _, body in pending.append(body) })

    controller.startMusic(fadeIn: 0)
    controller.stopMusic(fadeOut: 0)
    controller.startMusic(fadeIn: 0)

    pending.first?()

    XCTAssertTrue(controller.isMusicPlaying, "the first run's cap must not stop the second bed")
  }

  @MainActor
  func testTheCapIsTenSeconds() {
    XCTAssertEqual(OmiSoundController.maxMusicDuration, 10)
  }
}
