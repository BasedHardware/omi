import AVFoundation
import Foundation

//  Playback for the four sounds `scripts/make-sounds.py` generates into `Resources/Sounds`.
//
//  Two shapes, because they are two different things:
//
//  - `Sound.music` is the cinematic bed. It is *content*: it plays because the first-run cinematic
//    asked for it, so it answers to its own enable/mute control and never to the system's UI-sound
//    switch. It loops from one decoded `AVAudioPCMBuffer` with `.loops`, never by restarting the
//    container — `pad.m4a`'s last two seconds are crossfaded into its head, so the buffer is
//    sample-exact end to start while re-opening the file would put back exactly the seam that
//    crossfade exists to remove.
//  - `Sound.effect(_:)` fires one-shots off a pool of preloaded voices, so rapid overlapping clicks
//    neither allocate nor cut each other off. `click` and `swoosh` are interface chrome and honour
//    the system UI-sound setting.
//
//  Nothing here is allowed to fail loudly. Onboarding must not be able to break because a sound
//  file is missing or CoreAudio would not start: every path degrades to silence, logs once, and
//  returns to the caller immediately. All decoding and every HAL call happen on this file's own
//  serial queue, so a caller on the main actor never waits for either.

// MARK: - Assets

/// The four generated assets, named after their files.
enum SoundAsset: String, CaseIterable, Sendable {
    case pad, click, swoosh, chime

    /// ALAC in an MPEG-4 container: lossless, and small enough that the bed is 1.6 MB rather than
    /// the 275 MB the equivalent WAV would add to the repository.
    var fileName: String { "\(rawValue).m4a" }
}

/// A one-shot cue.
///
/// `pad` is deliberately not a case here. It is the looping bed, driven through `Sound.music`,
/// which has fades and a mute control that a one-shot has no use for — and firing the 24-second
/// bed as an effect is a mistake worth making unrepresentable.
enum SoundEffect: String, CaseIterable, Sendable {
    case click, swoosh, chime

    var asset: SoundAsset {
        switch self {
        case .click: return .click
        case .swoosh: return .swoosh
        case .chime: return .chime
        }
    }

    /// Interface chrome: feedback for something the user just did to the interface.
    ///
    /// This is exactly the class macOS's "Play user interface sound effects" setting governs, and
    /// the system applies it only to `NSSound`/`AudioServicesPlaySystemSound` — neither
    /// `AVAudioPlayer` nor `AVAudioEngine` consults it — so we have to apply it ourselves.
    ///
    /// `chime` is not chrome. It marks a permission actually being granted and the run actually
    /// finishing: a completion cue about the world changing, not a click on a control.
    var isChrome: Bool {
        switch self {
        case .click, .swoosh: return true
        case .chime: return false
        }
    }
}

// MARK: - Where the files are

/// Finds `<asset>.m4a` on disk.
///
/// `Resources/Sounds` is declared as a resource of the `ContextApp` target, so SwiftPM emits it
/// inside a `*.bundle` next to the binary and `scripts/build.sh` copies every such bundle into
/// `Contents/Resources`.
///
/// `Bundle.module` is deliberately not used, for the same reason `registerBundledFonts()` avoids
/// it: the generated accessor looks beside `Bundle.main.bundleURL` — wrong for an `.app`, where the
/// bundle lands one level down under `Contents/Resources` — then falls back to a path baked in on
/// the build machine, and `fatalError`s when neither exists. A missing sound must cost silence, not
/// the launch.
struct SoundAssetLocator {
    /// Searched in order; the first readable match wins.
    let roots: [URL]

    init(roots: [URL]) {
        self.roots = roots
    }

    func url(for asset: SoundAsset) -> URL? {
        for root in roots {
            let candidate = root.appendingPathComponent(asset.fileName)
            if FileManager.default.isReadableFile(atPath: candidate.path) { return candidate }
        }
        return nil
    }

    /// Every place an installed or locally built app can be keeping `Sounds/`.
    static let bundled = SoundAssetLocator(roots: bundledRoots())

    private static func bundledRoots() -> [URL] {
        guard let resources = Bundle.main.resourceURL else { return [] }
        // First: loose, the way the fonts ship. Nothing puts them there today, but it is the
        // cheapest check and it keeps this working if the bundle layout is ever flattened.
        var roots = [resources.appendingPathComponent("Sounds", isDirectory: true)]

        // Then any SwiftPM resource bundle, matched by its extension rather than by the mangled
        // name SwiftPM derives from the package name — that name is not ours to depend on, and it
        // changes if the package is ever renamed.
        let contents =
            (try? FileManager.default.contentsOfDirectory(at: resources, includingPropertiesForKeys: nil)) ?? []
        for bundle in contents where bundle.pathExtension == "bundle" {
            roots.append(bundle.appendingPathComponent("Sounds", isDirectory: true))
            roots.append(bundle.appendingPathComponent("Contents/Resources/Sounds", isDirectory: true))
        }
        return roots
    }
}

// MARK: - The system UI-sound setting

/// "Play user interface sound effects", from Sound settings.
///
/// There is no public API for it; the preference lives in `com.apple.systemsound` and is read
/// straight out of it. An absent key means on, which is the shipped default — a machine whose owner
/// has never touched the switch must still hear the interface.
enum SystemUISoundSetting {
    static func isEnabled() -> Bool {
        guard
            let value = CFPreferencesCopyAppValue(
                "com.apple.sound.uiaudio.enabled" as CFString,
                "com.apple.systemsound" as CFString)
        else { return true }
        guard let number = value as? NSNumber else { return true }
        return number.boolValue
    }
}

// MARK: - Fades

/// The shape of a volume ramp.
///
/// Equal power, not linear: a linear ramp on amplitude is heard as arriving late and leaving early,
/// because loudness is not linear in amplitude. `sin` over the quarter turn is the same curve a
/// crossfade uses, so a fade-out into a fade-in holds a constant perceived level.
enum SoundFade {
    /// - Parameter progress: 0…1 through the ramp. Values outside that clamp to the endpoints, so a
    ///   late timer tick can never overshoot past the target volume.
    static func amplitude(from start: Float, to end: Float, progress: Double) -> Float {
        if progress <= 0 { return start }
        if progress >= 1 { return end }
        let eased = Float(sin(progress * .pi / 2))
        return start + (end - start) * eased
    }
}

// MARK: - Output

/// Everything the layer above needs from CoreAudio.
///
/// One protocol so the decisions worth testing — chrome gating, missing assets, the bed's mute
/// control, fade defaults — run without an audio device. Every method returns immediately; the
/// implementation does its work on its own queue.
protocol SoundOutput: AnyObject {
    /// Decode each asset once and hold the PCM. Assets already loaded are left alone.
    func preload(_ assets: [SoundAsset: URL])
    /// Loop `asset` from its single decoded buffer, ramping up from silence over `fadeIn`.
    func startLoop(_ asset: SoundAsset, fadeIn: TimeInterval)
    /// Ramp the loop down over `fadeOut`, then stop it. Never a hard cut.
    func stopLoop(fadeOut: TimeInterval)
    /// Play `asset` once on a free voice.
    func playOneShot(_ asset: SoundAsset)
}

/// `SoundOutput` on `AVAudioEngine`.
final class AVSoundOutput: SoundOutput {
    /// One format for every node, so a mono asset (`click` is mono) can never be scheduled on a
    /// voice that was connected as stereo. Everything is converted to it at preload, once.
    static let canonicalFormat = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2)

    /// Enough voices that a click can overlap the three before it. Beyond that the oldest voice is
    /// reused, which is inaudible at these lengths (40–400 ms) and is bounded work.
    private static let voiceCount = 4
    private static let fadeInterval = 1.0 / 60.0
    /// Used when an audio device change forces a rebuild mid-bed: short, because the bed is already
    /// established and the user is not meant to notice the rebuild at all.
    private static let recoveryFadeIn: TimeInterval = 0.25
    private static let logCategory = "sound"

    /// Owns every field below and every HAL call. A caller on the main actor hands work over and
    /// returns; nothing here runs on their thread.
    private let queue = DispatchQueue(label: "com.omi.context-for-claude.sound", qos: .userInitiated)

    private let engine = AVAudioEngine()
    private let musicNode = AVAudioPlayerNode()
    private let musicMixer = AVAudioMixerNode()
    private var voices: [AVAudioPlayerNode] = []
    private var nextVoice = 0
    private var buffers: [SoundAsset: AVAudioPCMBuffer] = [:]

    private var isWired = false
    /// Latched: once the engine has refused to start, stop asking on every click.
    private var isSilenced = false
    private var loopingAsset: SoundAsset?
    private var fadeTimer: DispatchSourceTimer?
    private var configurationObserver: NSObjectProtocol?

    init() {
        // Plugging in headphones tears the engine's connections down. Without this the cinematic
        // bed would simply stop halfway through and never come back.
        configurationObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: engine,
            queue: nil
        ) { [weak self] _ in
            self?.queue.async { self?.rebuildAfterConfigurationChange() }
        }
    }

    deinit {
        if let configurationObserver {
            NotificationCenter.default.removeObserver(configurationObserver)
        }
        fadeTimer?.cancel()
    }

    // MARK: SoundOutput

    func preload(_ assets: [SoundAsset: URL]) {
        queue.async { [weak self] in
            guard let self else { return }
            for (asset, url) in assets where self.buffers[asset] == nil {
                guard let buffer = Self.decode(url, to: Self.canonicalFormat) else {
                    ContextLog.error("could not decode \(asset.fileName); that cue is silent", Self.logCategory)
                    continue
                }
                self.buffers[asset] = buffer
            }
        }
    }

    func startLoop(_ asset: SoundAsset, fadeIn: TimeInterval) {
        queue.async { [weak self] in self?.startLoopOnQueue(asset, fadeIn: fadeIn) }
    }

    func stopLoop(fadeOut: TimeInterval) {
        queue.async { [weak self] in
            guard let self, self.isWired else { return }
            self.loopingAsset = nil
            self.ramp(to: 0, over: fadeOut) { [weak self] in self?.musicNode.stop() }
        }
    }

    func playOneShot(_ asset: SoundAsset) {
        queue.async { [weak self] in
            guard let self,
                let buffer = self.buffers[asset],
                self.prepareEngineOnQueue(),
                let voice = self.claimVoiceOnQueue()
            else { return }

            voice.volume = 1
            // `.dataPlayedBack` fires after the audio has actually been heard, and stopping there is
            // what makes `isPlaying` false again — otherwise every voice reads as busy forever and
            // the pool degrades to round-robin cutting.
            voice.scheduleBuffer(buffer, at: nil, options: [], completionCallbackType: .dataPlayedBack) {
                [weak self, weak voice] _ in
                self?.queue.async { voice?.stop() }
            }
            voice.play()
        }
    }

    // MARK: Decoding

    /// Decodes the whole file into one buffer, converting to `format` when it does not already
    /// match. `nil` for anything unreadable, undecodable, or empty — all of which mean silence.
    static func decode(_ url: URL, to format: AVAudioFormat?) -> AVAudioPCMBuffer? {
        guard let format else { return nil }
        guard let file = try? AVAudioFile(forReading: url) else { return nil }

        let sourceFormat = file.processingFormat
        let frameCount = AVAudioFrameCount(max(0, file.length))
        guard frameCount > 0,
            let source = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: frameCount),
            (try? file.read(into: source)) != nil,
            source.frameLength > 0
        else { return nil }

        if sourceFormat == format { return source }

        guard let converter = AVAudioConverter(from: sourceFormat, to: format) else { return nil }
        let ratio = format.sampleRate / sourceFormat.sampleRate
        let capacity = AVAudioFrameCount((Double(source.frameLength) * ratio).rounded(.up)) + 4096
        guard let converted = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { return nil }

        var didSupply = false
        var error: NSError?
        let status = converter.convert(to: converted, error: &error) { _, outStatus in
            if didSupply {
                outStatus.pointee = .endOfStream
                return nil
            }
            didSupply = true
            outStatus.pointee = .haveData
            return source
        }
        guard status != .error, converted.frameLength > 0 else { return nil }
        return converted
    }

    // MARK: Engine, all on `queue`

    private func startLoopOnQueue(_ asset: SoundAsset, fadeIn: TimeInterval) {
        guard let buffer = buffers[asset], prepareEngineOnQueue() else { return }

        loopingAsset = asset
        musicNode.stop()
        musicMixer.outputVolume = fadeIn > 0 ? 0 : 1
        // `.loops` on the buffer, not `AVAudioPlayer.numberOfLoops`: the asset's tail is crossfaded
        // into its head, so looping the decoded PCM is sample-exact, while a container-level restart
        // reintroduces the seam the crossfade was generated to remove.
        musicNode.scheduleBuffer(buffer, at: nil, options: [.loops], completionHandler: nil)
        musicNode.play()
        ramp(to: 1, over: fadeIn, then: nil)
    }

    /// Wires the graph on first use and keeps the engine running. `false` means we are silent for
    /// the rest of the process, which every caller treats as "do nothing".
    private func prepareEngineOnQueue() -> Bool {
        if isSilenced { return false }
        if !isWired { wireOnQueue() }
        guard !isSilenced else { return false }
        guard !engine.isRunning else { return true }
        do {
            try engine.start()
            return true
        } catch {
            isSilenced = true
            ContextLog.error(
                "audio engine would not start (\(error.localizedDescription)); the app runs silent",
                Self.logCategory)
            return false
        }
    }

    private func wireOnQueue() {
        isWired = true
        guard let format = Self.canonicalFormat else {
            isSilenced = true
            ContextLog.error("no canonical audio format; the app runs silent", Self.logCategory)
            return
        }

        // A mixer of its own for the bed, so a fade is one volume ramp rather than a ramp per voice,
        // and so fading the music never touches the level of a click landing during the fade.
        engine.attach(musicMixer)
        engine.attach(musicNode)
        engine.connect(musicNode, to: musicMixer, format: format)
        engine.connect(musicMixer, to: engine.mainMixerNode, format: format)

        for _ in 0..<Self.voiceCount {
            let voice = AVAudioPlayerNode()
            engine.attach(voice)
            engine.connect(voice, to: engine.mainMixerNode, format: format)
            voices.append(voice)
        }
        engine.prepare()
    }

    /// An idle voice if there is one, so a click never truncates the click before it; otherwise the
    /// next in rotation, which needs more than `voiceCount` overlapping one-shots to reach.
    private func claimVoiceOnQueue() -> AVAudioPlayerNode? {
        if let idle = voices.first(where: { !$0.isPlaying }) { return idle }
        guard !voices.isEmpty else { return nil }
        let voice = voices[nextVoice % voices.count]
        nextVoice = (nextVoice + 1) % voices.count
        return voice
    }

    /// Ramps the bed's mixer. Replaces any ramp already in flight, so a stop during a fade-in starts
    /// from wherever the fade-in had got to instead of jumping to full volume first.
    private func ramp(to target: Float, over duration: TimeInterval, then completion: (() -> Void)?) {
        fadeTimer?.cancel()
        fadeTimer = nil

        guard duration > Self.fadeInterval else {
            musicMixer.outputVolume = target
            completion?()
            return
        }

        let start = musicMixer.outputVolume
        let startedAt = DispatchTime.now()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + Self.fadeInterval, repeating: Self.fadeInterval)
        timer.setEventHandler { [weak self] in
            guard let self else { return }
            let elapsed =
                Double(DispatchTime.now().uptimeNanoseconds - startedAt.uptimeNanoseconds) / 1_000_000_000
            let progress = elapsed / duration
            self.musicMixer.outputVolume = SoundFade.amplitude(from: start, to: target, progress: progress)
            guard progress >= 1 else { return }
            self.fadeTimer?.cancel()
            self.fadeTimer = nil
            completion?()
        }
        fadeTimer = timer
        timer.resume()
    }

    /// An audio device change (headphones, a display with speakers, a Bluetooth connect) stops the
    /// engine and drops its connections. Rebuild the graph and pick the bed back up; the decoded
    /// buffers survive, so this costs no decoding.
    private func rebuildAfterConfigurationChange() {
        guard isWired, !isSilenced else { return }
        let resume = loopingAsset

        fadeTimer?.cancel()
        fadeTimer = nil
        engine.stop()
        musicNode.stop()
        for voice in voices {
            voice.stop()
            engine.detach(voice)
        }
        voices.removeAll()
        nextVoice = 0
        engine.detach(musicNode)
        engine.detach(musicMixer)
        isWired = false
        loopingAsset = nil

        ContextLog.info("audio device changed; rebuilding the graph", Self.logCategory)
        guard let resume else { return }
        startLoopOnQueue(resume, fadeIn: Self.recoveryFadeIn)
    }
}

// MARK: - Policy

/// Decides what actually plays, and owns the one piece of state the cinematic reads back
/// (`isMusicPlaying`). Everything hardware lives behind `SoundOutput`.
@MainActor
final class SoundController {
    static let shared = SoundController(
        output: AVSoundOutput(),
        locator: .bundled,
        systemUISoundsEnabled: SystemUISoundSetting.isEnabled)

    /// The bed's own control. Persisted, because a user who mutes the music means it.
    static let musicEnabledDefaultsKey = "context.sound.musicEnabled"

    private let output: SoundOutput
    private let locator: SoundAssetLocator
    private let systemUISoundsEnabled: () -> Bool
    private let defaults: UserDefaults

    private var available: Set<SoundAsset> = []
    private var didPrepare = false

    init(
        output: SoundOutput,
        locator: SoundAssetLocator,
        systemUISoundsEnabled: @escaping () -> Bool,
        defaults: UserDefaults = .standard
    ) {
        self.output = output
        self.locator = locator
        self.systemUISoundsEnabled = systemUISoundsEnabled
        self.defaults = defaults
        // Absent means on: an install that has never seen the control still gets the cinematic.
        self.isMusicEnabled = defaults.object(forKey: Self.musicEnabledDefaultsKey) as? Bool ?? true
    }

    /// The bed is content, not chrome, so this — and never the system UI-sound setting — is what
    /// silences it. Turning it off while it plays fades it out rather than cutting it.
    var isMusicEnabled: Bool {
        didSet {
            guard isMusicEnabled != oldValue else { return }
            defaults.set(isMusicEnabled, forKey: Self.musicEnabledDefaultsKey)
            if !isMusicEnabled { stopMusic(fadeOut: SoundMusic.defaultFadeOut) }
        }
    }

    private(set) var isMusicPlaying = false

    /// Resolves every asset and hands the files over to be decoded. Idempotent, and cheap enough to
    /// call from a cue: the file checks are `stat`s and the decoding happens off this thread.
    func prepare() {
        guard !didPrepare else { return }
        didPrepare = true

        var found: [SoundAsset: URL] = [:]
        for asset in SoundAsset.allCases {
            guard let url = locator.url(for: asset) else {
                ContextLog.error("\(asset.fileName) is not in the bundle; that cue is silent", "sound")
                continue
            }
            found[asset] = url
        }
        available = Set(found.keys)
        output.preload(found)
    }

    /// Whether `effect` is allowed to be heard right now. Chrome answers to the system setting;
    /// everything else always plays.
    func allows(_ effect: SoundEffect) -> Bool {
        guard effect.isChrome else { return true }
        return systemUISoundsEnabled()
    }

    func play(_ effect: SoundEffect) {
        prepare()
        guard allows(effect), available.contains(effect.asset) else { return }
        output.playOneShot(effect.asset)
    }

    func startMusic(fadeIn: TimeInterval) {
        prepare()
        guard isMusicEnabled, available.contains(.pad), !isMusicPlaying else { return }
        isMusicPlaying = true
        output.startLoop(.pad, fadeIn: max(0, fadeIn))
    }

    func stopMusic(fadeOut: TimeInterval) {
        guard isMusicPlaying else { return }
        isMusicPlaying = false
        output.stopLoop(fadeOut: max(0, fadeOut))
    }
}

// MARK: - What the rest of the app calls

/// The looping cinematic bed.
@MainActor
final class SoundMusic {
    /// Long enough to read as the app arriving rather than as a sound starting. The dim it rides in
    /// under is ~0.6 s, so the bed is still arriving when the mark begins to draw.
    ///
    /// `nonisolated` so it can be a default argument: a main-actor-isolated constant cannot be read
    /// from the nonisolated position a default argument is evaluated in.
    nonisolated static let defaultFadeIn: TimeInterval = 1.6
    /// Shorter than the fade-in: leaving should feel decided, not reluctant.
    nonisolated static let defaultFadeOut: TimeInterval = 1.0

    private let controller: SoundController

    init(controller: SoundController) {
        self.controller = controller
    }

    /// The bed's own mute control — never the system UI-sound setting, which governs chrome.
    var isEnabled: Bool {
        get { controller.isMusicEnabled }
        set { controller.isMusicEnabled = newValue }
    }

    var isPlaying: Bool { controller.isMusicPlaying }

    func start(fadeIn: TimeInterval = SoundMusic.defaultFadeIn) {
        controller.startMusic(fadeIn: fadeIn)
    }

    func stop(fadeOut: TimeInterval = SoundMusic.defaultFadeOut) {
        controller.stopMusic(fadeOut: fadeOut)
    }
}

/// The app-facing surface. `Sound.music.start(fadeIn:)`, `Sound.effect(.swoosh)`.
@MainActor
enum Sound {
    static let music = SoundMusic(controller: .shared)

    static func effect(_ effect: SoundEffect) {
        SoundController.shared.play(effect)
    }

    /// Optional warm-up. Every cue calls this itself, so it exists only so the first click of the
    /// cinematic is not the thing that pays for decoding.
    static func prepare() {
        SoundController.shared.prepare()
    }
}
