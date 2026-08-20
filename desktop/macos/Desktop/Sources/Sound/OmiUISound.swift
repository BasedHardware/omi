import Foundation
import OmiTheme

//  Interface sounds for the whole app.
//
//  The engine, the four assets and the chrome-versus-content policy already exist: onboarding's
//  cinematic built them (`Sources/Onboarding/Cinematic/OmiOnboardingSound.swift`), and they are not
//  onboarding-shaped — one `AVAudioEngine` at 48 kHz, a four-voice pool for one-shots, every HAL
//  call on a private serial queue, and a latched degrade-to-silence on any failure. This file is the
//  part that was missing: a vocabulary for meaningful status changes the rest of the app can fire
//  without knowing which file plays, and the two gates that only make sense outside a two-minute
//  intro. Ordinary button activation is intentionally silent.
//
//  Those two gates are why this is not just `OmiOnboardingSound.effect(.click)` at every call site:
//
//  - **Reduce Motion.** A swoosh is the sound of a thing moving. When the user has asked the system
//    to stop things moving, the movement is gone and the sound describing it is left narrating an
//    animation that no longer happens.
//  - **Coalescing.** A cinematic fires cues from a script that runs once. The app fires them from
//    SwiftUI, where a single user action can re-enter a change handler several times in one frame.
//    Without a floor, one state change can become a burst, and a burst of cues is the difference
//    between an interface that responds and one that rattles.
//
//  Both gates and the mute are decided here, on the main actor, in nanoseconds. The work of actually
//  making a sound is still handed to the queue that owns the audio graph, so no call site ever waits
//  for CoreAudio.

// MARK: - The vocabulary

/// What the interface just did, not which file plays.
///
/// Call sites name the moment; the mapping to an effect lives here alone, so retuning the palette
/// is one edit rather than a search across the app.
enum OmiUICue: String, CaseIterable, Sendable {
  /// Something arrived: a panel stretching open, a toast landing.
  case reveal
  /// Something finished or landed: a turn completing, a permission being granted.
  case complete

  var effect: OmiSoundEffect {
    switch self {
    case .reveal: return .swoosh
    case .complete: return .chime
    }
  }

  /// Whether this cue is the voice of something moving on screen.
  ///
  /// Reduce Motion is a request about movement, and the app honours it by not moving. A cue that
  /// exists to accompany a movement has nothing left to accompany, so it does not fire; a cue that
  /// reports an event (a completion) still does, because that event still happened.
  var voicesMotion: Bool {
    switch self {
    case .reveal: return true
    case .complete: return false
    }
  }
}

// MARK: - Policy

/// Decides whether a cue is heard. Everything audible is `OmiSoundController`'s.
@MainActor
final class OmiUISoundService {
  static let shared = OmiUISoundService(controller: .shared)

  /// Two fires of the same cue closer together than this are one gesture arriving twice, not two
  /// gestures — SwiftUI re-entering a change handler within a frame. 80 ms is under the ~100 ms at
  /// which two cues stop being heard as one event and well over a frame, so it costs nothing a user
  /// could deliberately outrun.
  static let coalescingWindow: TimeInterval = 0.08

  private let controller: OmiSoundController
  private let reduceMotionEnabled: () -> Bool
  private let now: () -> TimeInterval
  private var lastFired: [OmiUICue: TimeInterval] = [:]

  init(
    controller: OmiSoundController,
    reduceMotionEnabled: @escaping () -> Bool = { InkReduceMotion.isEnabled },
    // Monotonic: unlike `Date`, it cannot be walked backwards by a clock correction mid-session.
    now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
  ) {
    self.controller = controller
    self.reduceMotionEnabled = reduceMotionEnabled
    self.now = now
  }

  /// The app's own mute, persisted, surfaced in Settings ▸ General. Separate from the system's
  /// "Play user interface sound effects" switch, which `OmiSoundController` applies to chrome only:
  /// this one silences chrome *and* content, because a user who mutes Omi means Omi.
  var isEnabled: Bool {
    get { controller.areEffectsEnabled }
    set { controller.areEffectsEnabled = newValue }
  }

  /// Whether `cue` would be heard right now, and why it would not. Pure; `play` is this plus the
  /// side effects.
  func allows(_ cue: OmiUICue) -> Bool {
    guard isEnabled else { return false }
    guard !(cue.voicesMotion && reduceMotionEnabled()) else { return false }
    return controller.allows(cue.effect)
  }

  /// Fires `cue` unless a gate or the coalescing window stops it. Never blocks: the gates are
  /// arithmetic and the playback is handed to the audio queue.
  func play(_ cue: OmiUICue) {
    guard allows(cue) else { return }

    let timestamp = now()
    if let last = lastFired[cue], timestamp - last < Self.coalescingWindow { return }
    lastFired[cue] = timestamp

    // One line per cue actually fired — bounded by the window above, so this is also the record
    // that shows a call site is firing once per action rather than once per frame.
    log("ui sound: \(cue.rawValue)")
    controller.play(cue.effect)
  }
}

// MARK: - What the rest of the app calls

/// One line at a call site: `OmiUISound.play(.complete)`.
@MainActor
enum OmiUISound {
  /// A unit test driving a completion boundary is not the running app reporting a visible event,
  /// and a test process has no business opening the audio HAL. This suppresses the
  /// *call sites*; the sound layer's own tests construct `OmiUISoundService` directly and still
  /// exercise every gate.
  private static let isRunningUnderXCTest: Bool =
    ProcessInfo.processInfo.environment["XCTestConfigurationFilePath"] != nil
    || NSClassFromString("XCTestCase") != nil

  static func play(_ cue: OmiUICue) {
    guard !isRunningUnderXCTest else { return }
    OmiUISoundService.shared.play(cue)
  }

  /// The Settings toggle's binding, and nothing else's.
  static var isEnabled: Bool {
    get { OmiUISoundService.shared.isEnabled }
    set { OmiUISoundService.shared.isEnabled = newValue }
  }
}
