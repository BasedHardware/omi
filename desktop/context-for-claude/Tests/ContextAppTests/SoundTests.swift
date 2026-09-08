import AVFoundation
import CoreAudio
import XCTest
@testable import ContextApp

/// Records what the layer above asked CoreAudio for, so the decisions worth asserting — chrome
/// gating, the bed's own mute control, missing assets, fades — run with no audio device involved.
private final class RecordingSoundOutput: SoundOutput {
    struct Loop: Equatable {
        let asset: SoundAsset
        let fadeIn: TimeInterval
    }

    var preloaded: [SoundAsset: URL] = [:]
    var loops: [Loop] = []
    var fadeOuts: [TimeInterval] = []
    var oneShots: [SoundAsset] = []

    func preload(_ assets: [SoundAsset: URL]) {
        preloaded.merge(assets) { _, new in new }
    }

    func startLoop(_ asset: SoundAsset, fadeIn: TimeInterval) {
        loops.append(Loop(asset: asset, fadeIn: fadeIn))
    }

    func stopLoop(fadeOut: TimeInterval) {
        fadeOuts.append(fadeOut)
    }

    func playOneShot(_ asset: SoundAsset) {
        oneShots.append(asset)
    }
}

final class SoundTests: XCTestCase {

    // MARK: - Fixtures

    /// The committed assets, found relative to this source file: the test bundle is not the app
    /// bundle, so `Bundle.main.resourceURL` cannot reach them here.
    private static let repositorySounds = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()  // ContextAppTests
        .deletingLastPathComponent()  // Tests
        .deletingLastPathComponent()  // package root
        .appendingPathComponent("Resources/Sounds", isDirectory: true)

    private var defaultsSuite = ""

    override func setUp() {
        super.setUp()
        // Its own domain: these tests set the music-mute default, and the machine running them is
        // also the machine the app runs on.
        defaultsSuite = "com.omi.context-for-claude.SoundTests.\(UUID().uuidString)"
    }

    override func tearDown() {
        UserDefaults.standard.removePersistentDomain(forName: defaultsSuite)
        super.tearDown()
    }

    private func makeDefaults() throws -> UserDefaults {
        try XCTUnwrap(UserDefaults(suiteName: defaultsSuite))
    }

    @MainActor
    private func makeController(
        roots: [URL],
        uiSoundsEnabled: Bool = true
    ) throws -> (SoundController, RecordingSoundOutput) {
        let output = RecordingSoundOutput()
        let controller = SoundController(
            output: output,
            locator: SoundAssetLocator(roots: roots),
            systemUISoundsEnabled: { uiSoundsEnabled },
            defaults: try makeDefaults())
        return (controller, output)
    }

    // MARK: - The assets reach the code

    /// Every asset the code names is a file that is actually committed, and every one of them decodes
    /// to a single non-empty buffer in the one format every node is wired with.
    ///
    /// This is the test that fails if `Resources/Sounds` stops being declared in `Package.swift`, if
    /// an asset is renamed, or if `make-sounds.py` emits something `AVAudioFile` cannot open.
    func testEveryAssetIsCommittedAndDecodesIntoOneBuffer() throws {
        let format = try XCTUnwrap(AVSoundOutput.canonicalFormat)

        for asset in SoundAsset.allCases {
            let url = Self.repositorySounds.appendingPathComponent(asset.fileName)
            XCTAssertTrue(FileManager.default.isReadableFile(atPath: url.path), asset.fileName)

            let buffer = try XCTUnwrap(AVSoundOutput.decode(url, to: format), asset.fileName)
            XCTAssertGreaterThan(buffer.frameLength, 0, asset.fileName)
            XCTAssertEqual(buffer.format.sampleRate, 48_000, asset.fileName)
            XCTAssertEqual(buffer.format.channelCount, 2, asset.fileName)
        }
    }

    /// The bed is decoded whole, once, rather than streamed: that is what lets `.loops` be seamless
    /// across the crossfaded loop point. A buffer that came back a fraction of a second long would
    /// mean we are looping a fragment.
    func testTheBedDecodesWholeSoItCanLoopFromOneBuffer() throws {
        let format = try XCTUnwrap(AVSoundOutput.canonicalFormat)
        let buffer = try XCTUnwrap(
            AVSoundOutput.decode(Self.repositorySounds.appendingPathComponent(SoundAsset.pad.fileName), to: format))

        let seconds = Double(buffer.frameLength) / buffer.format.sampleRate
        XCTAssertGreaterThan(seconds, 20, "the bed decoded to \(seconds)s — that is a fragment, not the loop")
    }

    /// Nothing readable anywhere is a normal state on a broken install, and it must produce `nil`
    /// rather than a URL that later fails to open.
    func testTheLocatorTakesTheFirstReadableRootAndOtherwiseReportsNothing() throws {
        let empty = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)

        XCTAssertNil(SoundAssetLocator(roots: []).url(for: .click))
        XCTAssertNil(SoundAssetLocator(roots: [empty]).url(for: .click))
        XCTAssertEqual(
            SoundAssetLocator(roots: [empty, Self.repositorySounds]).url(for: .click)?.lastPathComponent,
            SoundAsset.click.fileName)
    }

    // MARK: - Chrome honours the system setting

    /// `click` and `swoosh` are interface chrome. macOS applies "Play user interface sound effects"
    /// only to `NSSound`/`AudioServicesPlaySystemSound`, so an `AVAudioEngine` that does not check it
    /// keeps clicking at a user who switched interface sounds off.
    @MainActor
    func testChromeIsSilentWhenTheSystemUISoundSettingIsOff() throws {
        let (controller, output) = try makeController(roots: [Self.repositorySounds], uiSoundsEnabled: false)

        XCTAssertFalse(controller.allows(.click))
        XCTAssertFalse(controller.allows(.swoosh))

        controller.play(.click)
        controller.play(.swoosh)
        XCTAssertEqual(output.oneShots, [])
    }

    /// The same cues play when the setting is on, so the gate is the setting and not a mistake that
    /// silences chrome everywhere.
    @MainActor
    func testChromeIsHeardWhenTheSystemUISoundSettingIsOn() throws {
        let (controller, output) = try makeController(roots: [Self.repositorySounds], uiSoundsEnabled: true)

        controller.play(.click)
        controller.play(.swoosh)
        XCTAssertEqual(output.oneShots, [.click, .swoosh])
    }

    /// `chime` is not chrome: it marks a permission actually being granted and the run actually
    /// finishing. It is a completion cue about the world changing, not feedback on a control.
    @MainActor
    func testTheSuccessChimeIsNotChromeAndPlaysThroughTheSystemSetting() throws {
        let (controller, output) = try makeController(roots: [Self.repositorySounds], uiSoundsEnabled: false)

        XCTAssertFalse(SoundEffect.chime.isChrome)
        XCTAssertTrue(controller.allows(.chime))

        controller.play(.chime)
        XCTAssertEqual(output.oneShots, [.chime])
    }

    // MARK: - The bed is content, not chrome

    /// The music bed must not be silenced by the interface-sounds switch — it is content the
    /// cinematic asked for. Its own control is the only thing that stops it.
    @MainActor
    func testTheBedIgnoresTheSystemUISoundSettingAndAnswersOnlyToItsOwnControl() throws {
        let (controller, output) = try makeController(roots: [Self.repositorySounds], uiSoundsEnabled: false)

        controller.startMusic(fadeIn: SoundMusic.defaultFadeIn)
        XCTAssertTrue(controller.isMusicPlaying)
        XCTAssertEqual(output.loops, [.init(asset: .pad, fadeIn: SoundMusic.defaultFadeIn)])

        controller.isMusicEnabled = false
        XCTAssertFalse(controller.isMusicPlaying)
        XCTAssertEqual(output.fadeOuts.count, 1)

        controller.startMusic(fadeIn: SoundMusic.defaultFadeIn)
        XCTAssertFalse(controller.isMusicPlaying, "the bed's own mute control did not hold")
        XCTAssertEqual(output.loops.count, 1)
    }

    /// Muting mid-cinematic fades out. A hard cut is audible as a fault, which is the whole reason
    /// both directions take a duration.
    @MainActor
    func testEveryTransitionOfTheBedIsARampAndNeverAHardCut() throws {
        let (controller, output) = try makeController(roots: [Self.repositorySounds])

        controller.startMusic(fadeIn: SoundMusic.defaultFadeIn)
        controller.stopMusic(fadeOut: SoundMusic.defaultFadeOut)

        XCTAssertGreaterThan(SoundMusic.defaultFadeIn, 0)
        XCTAssertGreaterThan(SoundMusic.defaultFadeOut, 0)
        XCTAssertEqual(output.loops.first?.fadeIn, SoundMusic.defaultFadeIn)
        XCTAssertEqual(output.fadeOuts, [SoundMusic.defaultFadeOut])
    }

    /// The cinematic sequences beats and can ask for the bed more than once. Two loops playing over
    /// each other is a doubled bed, and stopping something that never started is not a fade.
    @MainActor
    func testStartingOrStoppingTheBedTwiceIsIdempotent() throws {
        let (controller, output) = try makeController(roots: [Self.repositorySounds])

        controller.startMusic(fadeIn: 1)
        controller.startMusic(fadeIn: 1)
        XCTAssertEqual(output.loops.count, 1)

        controller.stopMusic(fadeOut: 1)
        controller.stopMusic(fadeOut: 1)
        XCTAssertEqual(output.fadeOuts.count, 1)
    }

    // MARK: - Failure is silence

    /// Onboarding must not be able to fail because audio did. With nothing on disk every cue is a
    /// no-op: no crash, no exception, and no state claiming the bed is playing.
    @MainActor
    func testMissingAssetsDegradeToSilenceRatherThanFailing() throws {
        let missing = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let (controller, output) = try makeController(roots: [missing])

        controller.prepare()
        for effect in SoundEffect.allCases { controller.play(effect) }
        controller.startMusic(fadeIn: SoundMusic.defaultFadeIn)
        controller.stopMusic(fadeOut: SoundMusic.defaultFadeOut)

        XCTAssertEqual(output.preloaded, [:])
        XCTAssertEqual(output.oneShots, [])
        XCTAssertEqual(output.loops, [])
        XCTAssertEqual(output.fadeOuts, [])
        XCTAssertFalse(controller.isMusicPlaying)
    }

    /// A cue is allowed to be the first thing that touches audio, so preparation cannot be something
    /// a caller has to remember — and it must happen once, not per click.
    @MainActor
    func testTheFirstCuePreparesEveryAssetAndOnlyOnce() throws {
        let (controller, output) = try makeController(roots: [Self.repositorySounds])

        controller.play(.click)
        XCTAssertEqual(Set(output.preloaded.keys), Set(SoundAsset.allCases))

        output.preloaded.removeAll()
        controller.play(.click)
        controller.prepare()
        XCTAssertEqual(output.preloaded, [:], "assets were resolved and handed over more than once")
    }

    // MARK: - The ramp

    /// Clamped at both ends so a late timer tick cannot overshoot the target volume, monotonic in
    /// between, and equal-power rather than linear — a linear amplitude ramp is heard as arriving
    /// late and leaving early.
    func testTheFadeCurveIsClampedMonotonicAndEqualPower() {
        XCTAssertEqual(SoundFade.amplitude(from: 0, to: 1, progress: -0.5), 0)
        XCTAssertEqual(SoundFade.amplitude(from: 0, to: 1, progress: 0), 0)
        XCTAssertEqual(SoundFade.amplitude(from: 0, to: 1, progress: 1), 1)
        XCTAssertEqual(SoundFade.amplitude(from: 0, to: 1, progress: 4), 1)
        XCTAssertEqual(SoundFade.amplitude(from: 1, to: 0, progress: 1), 0)

        var previous = SoundFade.amplitude(from: 0, to: 1, progress: 0)
        for step in 1...20 {
            let value = SoundFade.amplitude(from: 0, to: 1, progress: Double(step) / 20)
            XCTAssertGreaterThan(value, previous)
            XCTAssertLessThanOrEqual(value, 1)
            previous = value
        }

        // Equal power: half way through the ramp is sin(π/4), not 0.5.
        XCTAssertEqual(SoundFade.amplitude(from: 0, to: 1, progress: 0.5), Float(sin(Double.pi / 4)), accuracy: 0.0001)
    }

    // MARK: - We never record ourselves

    /// Regression: the tap used to be built with an **empty** exclude list, i.e. a global tap over
    /// every process including this one. Now that the app plays sound, that means the cinematic's bed
    /// and swooshes — and every click a Settings surface plays during a live session — get recorded,
    /// transcribed, and filed in the user's own conversation history as if somebody had said them.
    ///
    /// Exercises the production factory both capture paths now call, not a copy of it.
    @available(macOS 14.4, *)
    func testEveryGlobalTapExcludesThisProcess() throws {
        let description = SystemAudioCapture.makeGlobalTapDescription(name: "test", uuid: UUID())
        let excluded: [AudioObjectID] = description.processes

        XCTAssertFalse(excluded.isEmpty, "a global tap with an empty exclude list records this app")

        // `CATapDescription` takes CoreAudio process *object* ids, not pids: a raw pid poured into an
        // `AudioObjectID` names some unrelated object, which would read exactly like a fix while our
        // own audio kept landing in the tap.
        let own = try XCTUnwrap(
            SystemAudioCapture.ownProcessObject(),
            "the HAL would not translate our own pid, so nothing could have been excluded")
        XCTAssertTrue(excluded.contains(own), "the tap excludes \(excluded), not this process (\(own))")
        XCTAssertEqual(SystemAudioCapture.excludedProcessObjects(), [own])
    }

    /// `processes` means the opposite thing depending on `exclusive`: with it off, a non-empty list is
    /// an *include* list and the tap would record only us. Inverting that flag would look like a
    /// tighter fix and would be total data loss, so the flag is asserted rather than assumed.
    @available(macOS 14.4, *)
    func testTheProcessListIsAnExcludeListAndTheTapStaysUnmuted() {
        let description = SystemAudioCapture.makeGlobalTapDescription(
            name: "test", uuid: UUID(), excluding: [4242])

        XCTAssertTrue(description.isExclusive, "the list is being read as an include list")
        XCTAssertEqual(description.processes, [4242])
        // `.unmuted` is not cosmetic: any other behaviour silences the user's own playback while we
        // are listening to it.
        XCTAssertEqual(description.muteBehavior, .unmuted)
    }
}
