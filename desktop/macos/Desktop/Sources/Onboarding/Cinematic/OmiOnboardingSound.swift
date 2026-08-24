import AVFoundation
import Foundation

//  Playback for the four sounds `scripts/make-onboarding-sounds.py` generates into
//  `Sources/Resources/Sounds`.
//
//  Two shapes, because they are two different things:
//
//  - `OmiOnboardingSound.music` is the ambient bed. It is *content*: it plays because onboarding
//    asked for it, so it answers to its own enable/mute control and never to the system's UI-sound
//    switch. It loops from one decoded `AVAudioPCMBuffer` with `.loops`, never by restarting the
//    container — `pad.m4a`'s last two seconds are crossfaded into its head, so the buffer is
//    sample-exact end to start while re-opening the file would put back exactly the seam that
//    crossfade exists to remove.
//  - `OmiOnboardingSound.effect(_:)` fires one-shots off a pool of preloaded voices, so rapid
//    overlapping clicks — eight of them land inside beat 2 — neither allocate nor cut each other
//    off. `click` and `swoosh` are interface chrome and honour the system UI-sound setting.
//
//  `AVAudioEngine` and not `AVAudioPlayer`, deliberately: the bed needs its own mixer node so a
//  fade never touches the level of a cue landing during it, the loop has to be sample-exact on
//  decoded PCM rather than a container restart, and the graph has to be rebuildable when the output
//  device changes underneath it. `AVAudioPlayer` gives none of those.
//
//  Nothing here is allowed to fail loudly. Onboarding must not be able to break because a sound
//  file is missing or CoreAudio would not start: every path degrades to silence, logs once, and
//  returns to the caller immediately. All decoding and every HAL call happen on this file's own
//  serial queue, so a caller on the main actor never waits for either.

// MARK: - Assets

/// The four generated assets, named after their files.
enum OmiSoundAsset: String, CaseIterable, Sendable {
  case pad, click, swoosh, chime

  /// ALAC in an MPEG-4 container: lossless, and small enough that the bed is 1.6 MB rather than
  /// the ~14 MB the equivalent WAV would add to the repository (which also gitignores `*.wav`).
  var fileName: String { "\(rawValue).m4a" }
}

/// A one-shot cue.
///
/// `pad` is deliberately not a case here. It is the looping bed, driven through
/// `OmiOnboardingSound.music`, which has fades and a mute control that a one-shot has no use for —
/// and firing the 24-second bed as an effect is a mistake worth making unrepresentable.
enum OmiSoundEffect: String, CaseIterable, Sendable {
  case click, swoosh, chime

  var asset: OmiSoundAsset {
    switch self {
    case .click: return .click
    case .swoosh: return .swoosh
    case .chime: return .chime
    }
  }

  /// Interface chrome: feedback for something the interface just did.
  ///
  /// This is exactly the class macOS's "Play user interface sound effects" setting governs, and the
  /// system applies it only to `NSSound`/`AudioServicesPlaySystemSound` — neither `AVAudioPlayer`
  /// nor `AVAudioEngine` consults it — so we have to apply it ourselves.
  ///
  /// `chime` is not chrome. It marks the run actually finishing: a completion cue about the world
  /// changing, not a click on a control.
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
/// `Resources/Sounds` is bundled by the executable target's `.process("Resources")` rule, so
/// SwiftPM emits it inside `Omi Computer_Omi Computer.bundle` and the build script copies that
/// bundle into `Contents/Resources`. `.process` may or may not preserve the `Sounds/`
/// subdirectory, exactly as `OmiFontRegistration` documents for `Fonts/`, so both shapes are
/// searched.
///
/// `Bundle.module` is deliberately not used, and neither is `Bundle.resourceBundle`: the former
/// looks beside `Bundle.main.bundleURL` — wrong for an `.app`, where the bundle lands one level
/// down under `Contents/Resources` — and both `fatalError` when the lookup fails. A missing sound
/// must cost silence, not the launch.
struct OmiSoundAssetLocator: Sendable {
  /// Searched in order; the first readable match wins.
  let roots: [URL]

  func url(for asset: OmiSoundAsset) -> URL? {
    for root in roots {
      let candidate = root.appendingPathComponent(asset.fileName)
      if FileManager.default.isReadableFile(atPath: candidate.path) { return candidate }
    }
    return nil
  }

  /// Every place an installed app, a locally built app, or a test host can be keeping `Sounds/`.
  static let bundled = OmiSoundAssetLocator(roots: bundledRoots())

  /// Bounded and non-fatal: a fixed set of containers, each checked flat and under `Sounds/`, plus
  /// any `*.bundle` sitting in them.
  static func bundledRoots() -> [URL] {
    let main = Bundle.main.bundleURL
    let containers: [URL] = [
      Bundle.main.resourceURL,
      main.appendingPathComponent("Contents/Resources"),
      main,
      // SwiftPM test host: the resource bundle is a sibling of the host binary's bundle.
      main.deletingLastPathComponent(),
    ].compactMap { $0 }

    var roots: [URL] = []
    var seen = Set<String>()
    func add(_ url: URL) {
      guard seen.insert(url.standardizedFileURL.path).inserted else { return }
      roots.append(url)
    }

    for container in containers {
      add(container.appendingPathComponent("Sounds", isDirectory: true))
      add(container)

      // Then any SwiftPM resource bundle, matched by its extension rather than by the mangled name
      // SwiftPM derives from the package name — that name changes if the package is renamed.
      let contents =
        (try? FileManager.default.contentsOfDirectory(at: container, includingPropertiesForKeys: nil)) ?? []
      for bundle in contents where bundle.pathExtension == "bundle" {
        add(bundle.appendingPathComponent("Sounds", isDirectory: true))
        add(bundle.appendingPathComponent("Contents/Resources/Sounds", isDirectory: true))
        add(bundle.appendingPathComponent("Contents/Resources", isDirectory: true))
        add(bundle)
      }
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
enum OmiSystemUISoundSetting {
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
enum OmiSoundFade {
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
protocol OmiSoundOutput: AnyObject, Sendable {
  /// Decode each asset once and hold the PCM. Assets already loaded are left alone.
  func preload(_ assets: [OmiSoundAsset: URL])
  /// Loop `asset` from its single decoded buffer, ramping up from silence over `fadeIn`.
  func startLoop(_ asset: OmiSoundAsset, fadeIn: TimeInterval)
  /// Ramp the loop down over `fadeOut`, then stop it. Never a hard cut.
  func stopLoop(fadeOut: TimeInterval)
  /// Play `asset` once on a free voice.
  func playOneShot(_ asset: OmiSoundAsset)
}

/// Hands one decoded buffer to `AVAudioConverter` exactly once, then reports end of stream.
///
/// A box rather than two captured locals because the converter's input block is `@Sendable` and an
/// `AVAudioPCMBuffer` is not. `@unchecked` is honest here: `convert(to:error:withInputFrom:)` runs
/// the block synchronously on the calling thread, so this is never touched from two places.
private final class OmiSoundConverterFeed: @unchecked Sendable {
  private let source: AVAudioPCMBuffer
  private var didSupply = false

  init(_ source: AVAudioPCMBuffer) {
    self.source = source
  }

  func next(_ outStatus: UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioPCMBuffer? {
    if didSupply {
      outStatus.pointee = .endOfStream
      return nil
    }
    didSupply = true
    outStatus.pointee = .haveData
    return source
  }
}

/// `OmiSoundOutput` on `AVAudioEngine`.
///
/// `@unchecked Sendable` because every stored property below is touched only from `queue`, a serial
/// queue this type owns: the AV graph types are not `Sendable` and cannot be made so, and confining
/// them to one queue is the guarantee the compiler cannot see.
final class OmiAVSoundOutput: OmiSoundOutput, @unchecked Sendable {
  /// One format for every node, so a mono asset (`click` is mono) can never be scheduled on a voice
  /// that was connected as stereo. Everything is converted to it at preload, once.
  ///
  /// Computed rather than stored, because the two toolchains disagree about the type. Xcode 16.4
  /// (what CI pins) does not see `AVAudioFormat` as `Sendable` and rejects it as shared mutable
  /// state; Swift 6.2 does see it as `Sendable` and rejects `nonisolated(unsafe)` as unnecessary.
  /// A computed property is global state to neither, so it compiles under both. Cost is one small
  /// allocation at preload and on a device-change rebuild — never per frame — and AVAudioEngine
  /// compares formats by value, so a fresh equal instance connects exactly as the stored one did.
  static var canonicalFormat: AVAudioFormat? {
    AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2)
  }

  /// Enough voices that a click can overlap the three before it. Beyond that the oldest voice is
  /// reused, which is inaudible at these lengths (40–400 ms) and is bounded work.
  private static let voiceCount = 4
  private static let fadeInterval = 1.0 / 60.0
  /// Used when an audio device change forces a rebuild mid-bed: short, because the bed is already
  /// established and the user is not meant to notice the rebuild at all.
  private static let recoveryFadeIn: TimeInterval = 0.25

  /// Owns every field below and every HAL call. A caller on the main actor hands work over and
  /// returns; nothing here runs on their thread.
  private let queue = DispatchQueue(label: "me.omi.onboarding.sound", qos: .userInitiated)

  private let engine = AVAudioEngine()
  private let musicNode = AVAudioPlayerNode()
  private let musicMixer = AVAudioMixerNode()
  private var voices: [AVAudioPlayerNode] = []
  private var nextVoice = 0
  private var buffers: [OmiSoundAsset: AVAudioPCMBuffer] = [:]

  private var isWired = false
  /// Permanent silence is reserved for an invalid graph/format. A transient engine-start failure
  /// remains retryable after the output device or audio configuration changes.
  private var isSilenced = false
  private var didLogEngineStartFailure = false
  private var loopingAsset: OmiSoundAsset?
  private var fadeTimer: DispatchSourceTimer?
  private var configurationObserver: NSObjectProtocol?

  init() {
    // Plugging in headphones tears the engine's connections down. Without this the bed would
    // simply stop halfway through onboarding and never come back.
    configurationObserver = NotificationCenter.default.addObserver(
      forName: .AVAudioEngineConfigurationChange,
      object: engine,
      queue: nil
    ) { [weak self] _ in
      // Bound once: the inner block is `@Sendable` too, and re-reading a weak capture inside it is
      // a second capture the compiler cannot prove safe.
      guard let self else { return }
      self.queue.async { self.rebuildAfterConfigurationChange() }
    }
  }

  deinit {
    if let configurationObserver {
      NotificationCenter.default.removeObserver(configurationObserver)
    }
    fadeTimer?.cancel()
  }

  // MARK: OmiSoundOutput

  func preload(_ assets: [OmiSoundAsset: URL]) {
    queue.async { [weak self] in
      guard let self else { return }
      for (asset, url) in assets where self.buffers[asset] == nil {
        guard let buffer = Self.decode(url, to: Self.canonicalFormat) else {
          logError("onboarding sound: could not decode \(asset.fileName); that cue is silent")
          continue
        }
        self.buffers[asset] = buffer
      }
    }
  }

  func startLoop(_ asset: OmiSoundAsset, fadeIn: TimeInterval) {
    queue.async { [weak self] in self?.startLoopOnQueue(asset, fadeIn: fadeIn) }
  }

  func stopLoop(fadeOut: TimeInterval) {
    queue.async { [weak self] in
      guard let self, self.isWired else { return }
      self.loopingAsset = nil
      // `ramp` always calls back on `queue`, so this is already on the queue that owns the graph.
      self.ramp(to: 0, over: fadeOut) { [weak self] in
        self?.musicNode.stop()
        self?.stopEngineIfIdleOnQueue()
      }
    }
  }

  func playOneShot(_ asset: OmiSoundAsset) {
    queue.async { [weak self] in
      guard let self,
        let buffer = self.buffers[asset],
        self.prepareEngineOnQueue(),
        let index = self.claimVoiceIndexOnQueue()
      else { return }

      let voice = self.voices[index]
      voice.volume = 1
      // `.dataPlayedBack` fires after the audio has actually been heard, and stopping there is what
      // makes `isPlaying` false again — otherwise every voice reads as busy forever and the pool
      // degrades to round-robin cutting.
      //
      // The callback carries the voice's *index*, never the node: the completion block is
      // `@Sendable` and an `AVAudioPlayerNode` is not, so the node is looked back up on the queue
      // that owns it. A rebuild that has emptied `voices` in the meantime finds nothing and stops.
      voice.scheduleBuffer(buffer, at: nil, options: [], completionCallbackType: .dataPlayedBack) {
        [weak self] _ in
        guard let self else { return }
        self.queue.async { self.stopVoiceOnQueue(at: index) }
      }
      voice.play()
    }
  }

  // MARK: Decoding

  /// Decodes the whole file into one buffer, converting to `format` when it does not already match.
  /// `nil` for anything unreadable, undecodable, or empty — all of which mean silence.
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

    // `AVAudioConverterInputBlock` is `@Sendable`, so the source buffer and the "already supplied"
    // flag cannot be captured directly. Both live in one box the block owns instead; the whole
    // conversion is synchronous on this thread, which is the confinement `@unchecked` stands for.
    let feed = OmiSoundConverterFeed(source)
    var error: NSError?
    let status = converter.convert(to: converted, error: &error) { _, outStatus in
      feed.next(outStatus)
    }
    guard status != .error, converted.frameLength > 0 else { return nil }
    return converted
  }

  // MARK: Engine, all on `queue`

  private func startLoopOnQueue(_ asset: OmiSoundAsset, fadeIn: TimeInterval) {
    guard let buffer = buffers[asset], prepareEngineOnQueue() else { return }

    loopingAsset = asset
    musicNode.stop()
    musicMixer.outputVolume = fadeIn > 0 ? 0 : 1
    // `.loops` on the buffer, not a container restart: the asset's tail is crossfaded into its
    // head, so looping the decoded PCM is sample-exact, while re-opening the file reintroduces the
    // seam the crossfade was generated to remove.
    musicNode.scheduleBuffer(buffer, at: nil, options: [.loops], completionHandler: nil)
    musicNode.play()
    ramp(to: 1, over: fadeIn, then: nil)
  }

  /// Wires the graph on first use and starts the engine, restarting it if `stopEngineIfIdleOnQueue`
  /// has since parked it. `false` means we are silent for the rest of the process, which every
  /// caller treats as "do nothing".
  private func prepareEngineOnQueue() -> Bool {
    if isSilenced { return false }
    if !isWired { wireOnQueue() }
    guard !isSilenced else { return false }
    guard !engine.isRunning else { return true }
    do {
      try engine.start()
      didLogEngineStartFailure = false
      return true
    } catch {
      if !didLogEngineStartFailure {
        didLogEngineStartFailure = true
        logError("onboarding sound: audio engine would not start; will retry", error: error)
      }
      return false
    }
  }

  private func wireOnQueue() {
    isWired = true
    guard let format = Self.canonicalFormat else {
      isSilenced = true
      logError("onboarding sound: no canonical audio format; onboarding runs silent")
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
  private func claimVoiceIndexOnQueue() -> Int? {
    if let idle = voices.firstIndex(where: { !$0.isPlaying }) { return idle }
    guard !voices.isEmpty else { return nil }
    let index = nextVoice % voices.count
    nextVoice = (nextVoice + 1) % voices.count
    return index
  }

  private func stopVoiceOnQueue(at index: Int) {
    guard voices.indices.contains(index) else { return }
    voices[index].stop()
    stopEngineIfIdleOnQueue()
  }

  /// Stops the engine once nothing is scheduled on it.
  ///
  /// A running `AVAudioEngine` holds a HAL I/O proc open and its render thread awake for the life
  /// of the process, whether or not anything is audible. Onboarding plays for a couple of minutes
  /// and the controller is a singleton, so leaving it running meant every session after the intro
  /// paid for an audio graph rendering silence. The graph itself is kept wired — `wireOnQueue` is
  /// the expensive part and `prepareEngineOnQueue` restarts a stopped engine on the next cue, so a
  /// click after the bed has faded still sounds.
  private func stopEngineIfIdleOnQueue() {
    guard isWired, engine.isRunning else { return }
    guard loopingAsset == nil, !musicNode.isPlaying else { return }
    guard !voices.contains(where: { $0.isPlaying }) else { return }
    engine.stop()
  }

  /// Ramps the bed's mixer. Replaces any ramp already in flight, so a stop during a fade-in starts
  /// from wherever the fade-in had got to instead of jumping to full volume first.
  private func ramp(to target: Float, over duration: TimeInterval, then completion: (@Sendable () -> Void)?) {
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
      self.musicMixer.outputVolume = OmiSoundFade.amplitude(from: start, to: target, progress: progress)
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

    log("onboarding sound: audio device changed; rebuilding the graph")
    guard let resume else { return }
    startLoopOnQueue(resume, fadeIn: Self.recoveryFadeIn)
  }
}

// MARK: - Policy

/// Decides what actually plays, and owns the one piece of state the cinematic reads back
/// (`isMusicPlaying`). Everything hardware lives behind `OmiSoundOutput`.
@MainActor
final class OmiSoundController {
  static let shared = OmiSoundController(
    output: OmiAVSoundOutput(),
    locator: .bundled,
    systemUISoundsEnabled: OmiSystemUISoundSetting.isEnabled)

  /// The bed's own control. Persisted, because a user who mutes the music means it.
  static let musicEnabledDefaultsKey = "omi.onboarding.sound.musicEnabled"

  /// The app's mute for one-shot cues, wherever they are fired from. Persisted, and surfaced as the
  /// Settings ▸ General "Interface Sounds" row once the app is past onboarding.
  ///
  /// It lives here rather than in `OmiUISoundService` so that it is the one mute: onboarding fires
  /// cues straight through this controller, and a user who turned Omi's sounds off and then ran
  /// onboarding again would otherwise be told the switch had not been honoured. The bed keeps its
  /// own control above — it is content with a visible toggle of its own inside the cinematic, and a
  /// second switch silently overriding that one would make that toggle look broken.
  static let effectsEnabledDefaultsKey = "omi.sound.effectsEnabled"

  private let output: OmiSoundOutput
  private let locator: OmiSoundAssetLocator
  private let systemUISoundsEnabled: () -> Bool
  private let defaults: UserDefaults

  /// How long the bed is allowed to play before it fades itself out.
  ///
  /// The bed loops from one decoded buffer with `.loops`, so without a cap it plays
  /// for as long as the process lives — nothing in the cinematic stops it if the
  /// user leaves onboarding open, and that is what is heard as intro music that
  /// never ends. Ten seconds is enough to read as the app arriving.
  static let maxMusicDuration: TimeInterval = 10

  private var available: Set<OmiSoundAsset> = []
  private var didPrepare = false
  /// Bumped whenever the bed starts or stops, so a cap scheduled for an older run
  /// recognises itself as stale instead of cutting a bed someone started since.
  private var musicGeneration = 0
  private let scheduleCap: (TimeInterval, @escaping @Sendable () -> Void) -> Void

  init(
    output: OmiSoundOutput,
    locator: OmiSoundAssetLocator,
    systemUISoundsEnabled: @escaping () -> Bool,
    defaults: UserDefaults = .standard,
    // Injectable so the cap is testable without a wall-clock wait.
    scheduleCap: @escaping (TimeInterval, @escaping @Sendable () -> Void) -> Void = { delay, body in
      DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: body)
    }
  ) {
    self.output = output
    self.locator = locator
    self.systemUISoundsEnabled = systemUISoundsEnabled
    self.defaults = defaults
    self.scheduleCap = scheduleCap
    // Absent means on: an install that has never seen the control still gets the bed.
    self.isMusicEnabled = defaults.object(forKey: Self.musicEnabledDefaultsKey) as? Bool ?? true
    self.areEffectsEnabled = defaults.object(forKey: Self.effectsEnabledDefaultsKey) as? Bool ?? true
  }

  /// The app's mute. Off means no cue reaches the audio graph, chrome or content.
  var areEffectsEnabled: Bool {
    didSet {
      guard areEffectsEnabled != oldValue else { return }
      defaults.set(areEffectsEnabled, forKey: Self.effectsEnabledDefaultsKey)
    }
  }

  /// The bed is content, not chrome, so this — and never the system UI-sound setting — is what
  /// silences it. Turning it off while it plays fades it out rather than cutting it.
  var isMusicEnabled: Bool {
    didSet {
      guard isMusicEnabled != oldValue else { return }
      defaults.set(isMusicEnabled, forKey: Self.musicEnabledDefaultsKey)
      if !isMusicEnabled { stopMusic(fadeOut: OmiOnboardingMusic.defaultFadeOut) }
    }
  }

  private(set) var isMusicPlaying = false

  /// Resolves every asset and hands the files over to be decoded. Idempotent, and cheap enough to
  /// call from a cue: the file checks are `stat`s and the decoding happens off this thread.
  func prepare() {
    guard !didPrepare else { return }
    didPrepare = true

    var found: [OmiSoundAsset: URL] = [:]
    for asset in OmiSoundAsset.allCases {
      guard let url = locator.url(for: asset) else {
        logError("onboarding sound: \(asset.fileName) is not in the bundle; that cue is silent")
        continue
      }
      found[asset] = url
    }
    available = Set(found.keys)
    output.preload(found)
  }

  /// Which assets `prepare()` actually resolved. Read by tests; the app never branches on it.
  var availableAssets: Set<OmiSoundAsset> { available }

  /// Whether `effect` is allowed to be heard right now. The app's own mute silences everything;
  /// past it, chrome answers to the system setting and content always plays.
  func allows(_ effect: OmiSoundEffect) -> Bool {
    guard areEffectsEnabled else { return false }
    guard effect.isChrome else { return true }
    return systemUISoundsEnabled()
  }

  func play(_ effect: OmiSoundEffect) {
    prepare()
    guard allows(effect), available.contains(effect.asset) else { return }
    output.playOneShot(effect.asset)
  }

  func startMusic(fadeIn: TimeInterval) {
    prepare()
    guard isMusicEnabled, available.contains(.pad), !isMusicPlaying else { return }
    isMusicPlaying = true
    output.startLoop(.pad, fadeIn: max(0, fadeIn))
    scheduleMusicCap()
  }

  func stopMusic(fadeOut: TimeInterval) {
    musicGeneration &+= 1
    guard isMusicPlaying else { return }
    isMusicPlaying = false
    output.stopLoop(fadeOut: max(0, fadeOut))
  }

  /// Fades the bed out once its allowance is spent, so a loop that nothing else
  /// stops cannot keep playing for the life of the process.
  private func scheduleMusicCap() {
    musicGeneration &+= 1
    let generation = musicGeneration
    scheduleCap(Self.maxMusicDuration) { [weak self] in
      MainActor.assumeIsolated {
        guard let self, self.musicGeneration == generation, self.isMusicPlaying else { return }
        // Logged because the cap is otherwise only audible: without this line the
        // only way to tell a build has it is to sit and listen to onboarding.
        log("onboarding sound: bed reached its \(Int(Self.maxMusicDuration))s cap; fading out")
        self.stopMusic(fadeOut: OmiOnboardingMusic.defaultFadeOut)
      }
    }
  }
}

// MARK: - What the rest of the app calls

/// The looping ambient bed. Started by the cinematic's first beat, and by the chat-style onboarding
/// when it runs without the intro.
@MainActor
final class OmiOnboardingMusic {
  /// Long enough to read as the app arriving rather than as a sound starting. The dim it rides in
  /// under is ~0.6 s, so the bed is still arriving when the first dot lands.
  ///
  /// `nonisolated` so it can be a default argument: a main-actor-isolated constant cannot be read
  /// from the nonisolated position a default argument is evaluated in.
  nonisolated static let defaultFadeIn: TimeInterval = 1.6
  /// Shorter than the fade-in: leaving should feel decided, not reluctant.
  nonisolated static let defaultFadeOut: TimeInterval = 1.0

  private let controller: OmiSoundController

  init(controller: OmiSoundController) {
    self.controller = controller
  }

  /// The bed's own mute control — never the system UI-sound setting, which governs chrome.
  var isEnabled: Bool {
    get { controller.isMusicEnabled }
    set { controller.isMusicEnabled = newValue }
  }

  var isPlaying: Bool { controller.isMusicPlaying }

  func start(fadeIn: TimeInterval = OmiOnboardingMusic.defaultFadeIn) {
    controller.startMusic(fadeIn: fadeIn)
  }

  func stop(fadeOut: TimeInterval = OmiOnboardingMusic.defaultFadeOut) {
    controller.stopMusic(fadeOut: fadeOut)
  }
}

/// The app-facing surface. `OmiOnboardingSound.music.start()`, `OmiOnboardingSound.effect(.swoosh)`.
@MainActor
enum OmiOnboardingSound {
  static let music = OmiOnboardingMusic(controller: .shared)

  static func effect(_ effect: OmiSoundEffect) {
    OmiSoundController.shared.play(effect)
  }

  /// Optional warm-up. Every cue calls this itself, so it exists only so the first click of the
  /// cinematic is not the thing that pays for decoding.
  static func prepare() {
    OmiSoundController.shared.prepare()
  }
}
