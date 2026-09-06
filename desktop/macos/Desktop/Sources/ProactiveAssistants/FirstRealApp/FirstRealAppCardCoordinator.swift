import AppKit
import Combine
import Foundation
import VoiceTurnDomain

/// A cancellable piece of future work. One protocol for the dwell delay and the
/// card timeout so both are driven by the same injected clock in tests — no
/// `Task.sleep`, no wall-clock waits, and no 60-second unit test.
protocol FirstRealAppCardScheduledWork: AnyObject {
  @MainActor func cancel()
}

@MainActor
protocol FirstRealAppCardScheduling {
  func schedule(
    after delay: TimeInterval,
    _ work: @escaping @MainActor () -> Void
  ) -> FirstRealAppCardScheduledWork
}

/// Production scheduler: the main run loop.
@MainActor
struct FirstRealAppCardMainQueueScheduler: FirstRealAppCardScheduling {
  private final class Work: FirstRealAppCardScheduledWork {
    let item: DispatchWorkItem
    init(_ item: DispatchWorkItem) { self.item = item }
    @MainActor func cancel() { item.cancel() }
  }

  func schedule(
    after delay: TimeInterval,
    _ work: @escaping @MainActor () -> Void
  ) -> FirstRealAppCardScheduledWork {
    let item = DispatchWorkItem { MainActor.assumeIsolated { work() } }
    DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: item)
    return Work(item)
  }
}

/// The first-real-app tap-to-ask card: once per fresh install, the first time
/// the user brings a real app to the front after onboarding, Omi says it can
/// see it and offers the two ways to ask about it.
///
/// **Why the card exists.** A third of new macOS users never ask a single
/// question. The best-performing first question is about the screen — but 19%
/// of those were asked while Omi's own window was frontmost, so Omi described
/// its own onboarding. Meanwhile notch cards convert at ~2% because they are
/// dead ends: nothing on them opens Ask Omi, and push-to-talk is discoverable
/// only as two hover lines. This card is the one that is not a dead end.
///
/// **Split.** Exactly the shape `IntegrationNudgeCoordinator` uses: this type
/// owns the `NSWorkspace.didActivateApplicationNotification` observation, the
/// dwell, delivery and dismissal; `FirstRealAppCardPolicy` — pure and
/// clock-free — decides. Everything with a clock in it goes through the
/// injected scheduler, so the dwell and the 60s timeout are unit-testable.
///
/// **Delivery** goes through `NotificationService` with `respectFrequency:
/// false` — the proactive frequency slider ships at 0 (Off), and this is a
/// first-run activation moment, not a proactive suggestion — and
/// `isPersistent: true`, so nothing but the exits below takes it down.
@MainActor
final class FirstRealAppCardCoordinator {
  static let shared = FirstRealAppCardCoordinator()

  /// The `assistantId` this feature's card carries. Selects `FirstRealAppCard`
  /// in `FloatingControlBarView.barNotification`, and scopes every dismissal so
  /// this coordinator can never take down somebody else's card.
  static let assistantID = "first_real_app"

  /// Sends the card. Injected so delivery can be observed without a window
  /// server or a signed-in session.
  typealias Presenter = @MainActor (_ ownerID: String, _ title: String, _ body: String) -> Void

  /// Takes the card down, if it is still ours.
  typealias Dismisser = @MainActor (_ kind: NotificationDismissalKind) -> Void

  /// Asks push-to-talk to have a microphone capture running before the press
  /// this card is about to invite. Injected so the test suite observes the
  /// request without opening a real device.
  ///
  /// The card is the one moment in a fresh install where the next press is
  /// predictable, and the press it invites is the one measured failing:
  /// `capture_never_operational` is the largest PTT failure class among users
  /// who just completed onboarding. This claims no voice lifecycle (INV-VOICE-1)
  /// — it parks a capture, it does not start a turn.
  typealias WarmCaptureRequest = @MainActor () -> Void

  /// Installs an observation of "a push-to-talk turn started" and returns the
  /// teardown. The card claims no voice lifecycle of its own — INV-VOICE-1
  /// allows exactly one owner and that is `VoiceTurnCoordinator` — so this only
  /// watches the snapshots it already publishes.
  typealias PTTObserver = @MainActor (_ onStart: @escaping @MainActor () -> Void) -> (@MainActor () -> Void)

  /// The app-wide switches one decision depends on, read together at decision
  /// time and injected so tests never touch process-wide state.
  struct Environment {
    var isOnboardingComplete: Bool
    /// The signed-in owner the card would be fenced to. `nil` is "signed out",
    /// which is both the policy's sign-in gate and the value delivery needs, so
    /// it is read once rather than twice with a window in between.
    var ownerID: String?
    var pttChordTokens: [String]
    var omiBundleIdentifier: String?

    @MainActor
    static var live: Environment {
      Environment(
        isOnboardingComplete: UserDefaults.standard.bool(forKey: .hasCompletedOnboarding),
        ownerID: RuntimeOwnerIdentity.currentOwnerId(),
        pttChordTokens: ShortcutSettings.shared.pttShortcut.displayTokens,
        omiBundleIdentifier: Bundle.main.bundleIdentifier
      )
    }
  }

  private let defaults: UserDefaults
  private let environment: @MainActor () -> Environment
  private let frontmostApp: @MainActor () -> (bundleIdentifier: String?, localizedName: String?)
  private let presenter: Presenter
  private let dismisser: Dismisser
  private let pttObserver: PTTObserver
  private let warmCapture: WarmCaptureRequest
  private let openChat: @MainActor (_ prompt: String) -> Void
  private let scheduler: any FirstRealAppCardScheduling

  private var activationObserver: NSObjectProtocol?
  private var defaultsObserver: NSObjectProtocol?
  private var dwell: FirstRealAppCardScheduledWork?
  private var timeout: FirstRealAppCardScheduledWork?
  private var stopObservingPTT: (@MainActor () -> Void)?
  /// True between delivery and the card's one terminal phase. Guarantees the
  /// funnel gets at most one terminal event per card, whichever exit wins the
  /// race (a tap that lands as the timeout fires, say).
  private var cardIsLive = false

  init(
    defaults: UserDefaults = .standard,
    environment: @escaping @MainActor () -> Environment = { .live },
    frontmostApp: @escaping @MainActor () -> (bundleIdentifier: String?, localizedName: String?) = {
      let app = NSWorkspace.shared.frontmostApplication
      return (app?.bundleIdentifier, app?.localizedName)
    },
    presenter: @escaping Presenter = FirstRealAppCardCoordinator.notificationServicePresenter,
    dismisser: @escaping Dismisser = FirstRealAppCardCoordinator.floatingBarDismisser,
    pttObserver: @escaping PTTObserver = FirstRealAppCardCoordinator.voiceTurnPTTObserver,
    warmCapture: @escaping WarmCaptureRequest = {
      PushToTalkManager.shared.prewarmMicCapture(trigger: .firstRealAppCard)
    },
    openChat: @escaping @MainActor (String) -> Void = { prompt in
      // The seam every prefill already uses. `MainChatNavigationRequestStore`
      // holds the draft until a composer mounts, so this works whether or not
      // the main window exists yet — and it never sends.
      AppDelegate.summonWindowTarget()?.openMainAppChat(prefilledDraft: prompt)
    },
    scheduler: any FirstRealAppCardScheduling = FirstRealAppCardMainQueueScheduler()
  ) {
    self.defaults = defaults
    self.environment = environment
    self.frontmostApp = frontmostApp
    self.presenter = presenter
    self.dismisser = dismisser
    self.pttObserver = pttObserver
    self.warmCapture = warmCapture
    self.openChat = openChat
    self.scheduler = scheduler
  }

  // MARK: - Live effects

  /// Owner-fenced delivery, same gates as every other proactive card except the
  /// frequency slider — see the type doc for why that one is bypassed.
  static let notificationServicePresenter: Presenter = { ownerID, title, body in
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else { return }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: title,
      message: body,
      assistantId: FirstRealAppCardCoordinator.assistantID,
      sound: .none,
      action: .askOmiPrefilled(prompt: FirstRealAppCardPolicy.prompt),
      respectFrequency: false,
      isPersistent: true,
      authorizationSnapshot: snapshot
    )
  }

  /// Dismiss by identity, not by position: the bar exposes only "dismiss the
  /// current card", so this refuses unless the current card is this feature's.
  /// Without the check, a 60-second timeout armed for our card could retire a
  /// meeting-summary card that displaced it in the meantime.
  static let floatingBarDismisser: Dismisser = { kind in
    let manager = FloatingControlBarManager.shared
    guard manager.window?.state.currentNotification?.assistantId == assistantID else { return }
    manager.dismissCurrentNotification(kind: kind)
  }

  /// Push-to-talk start, observed rather than owned: a turn appearing in the
  /// voice coordinator's published snapshot is exactly the moment
  /// `PushToTalkManager` calls `begin(intent:)`, on both the hold and the
  /// locked path.
  static let voiceTurnPTTObserver: PTTObserver = { onStart in
    // `observeSnapshots` replays the current snapshot synchronously on
    // subscribe. A turn already in flight at that moment (the user held the
    // chord during the dwell) must not retire the card before it is seen; only
    // a turn that begins after subscription counts as "PTT after the card".
    var replayedTurnID: VoiceTurnID?
    var isReplay = true
    let observation = VoiceTurnCoordinator.shared.observeSnapshots { model in
      if isReplay {
        isReplay = false
        replayedTurnID = model.turn?.id
        return
      }
      guard let turn = model.turn, !turn.phase.isTerminal, turn.id != replayedTurnID else { return }
      onStart()
    }
    return { observation.cancel() }
  }

  // MARK: - Lifecycle

  /// Run the install gate, then start watching for the first real app — as soon
  /// as onboarding is complete, which may be now or may be several minutes from
  /// now. Observing the completion rather than reading it once at launch is the
  /// whole difference between the card working on a fresh install and never
  /// firing at all: at launch on a first run, onboarding has not finished.
  func start() {
    runInstallGate()
    guard state == .pending else { return }
    beginObservingActivationsIfReady()
    guard activationObserver == nil, defaultsObserver == nil else { return }
    defaultsObserver = NotificationCenter.default.addObserver(
      forName: UserDefaults.didChangeNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.beginObservingActivationsIfReady()
      }
    }
  }

  func stop() {
    if let activationObserver {
      NSWorkspace.shared.notificationCenter.removeObserver(activationObserver)
      self.activationObserver = nil
    }
    if let defaultsObserver {
      NotificationCenter.default.removeObserver(defaultsObserver)
      self.defaultsObserver = nil
    }
    dwell?.cancel()
    dwell = nil
    retireCard(phase: nil, dismissKind: nil)
  }

  /// Idempotent: the defaults observer fires on every write, and only the first
  /// one that finds onboarding complete installs anything.
  func beginObservingActivationsIfReady() {
    guard activationObserver == nil, state == .pending, environment().isOnboardingComplete else {
      return
    }
    if let defaultsObserver {
      NotificationCenter.default.removeObserver(defaultsObserver)
      self.defaultsObserver = nil
    }
    activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
      forName: NSWorkspace.didActivateApplicationNotification,
      object: nil,
      queue: .main
    ) { [weak self] notification in
      let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
      let bundleIdentifier = app?.bundleIdentifier
      let appName = app?.localizedName
      MainActor.assumeIsolated {
        self?.handleActivation(bundleIdentifier: bundleIdentifier, appName: appName)
      }
    }
    log("FirstRealAppCardCoordinator: watching for the first real app")
  }

  // MARK: - Install gate

  /// Version gate, run once per install on the first launch of a build that has
  /// this feature. See `FirstRealAppCardPolicy.installGate`.
  private func runInstallGate() {
    let gate = FirstRealAppCardPolicy.installGate(
      state: state,
      hasCompletedOnboarding: environment().isOnboardingComplete
    )
    guard case .record(let verdict) = gate else { return }
    write(verdict)
    log("FirstRealAppCardCoordinator: install gate recorded \(verdict.rawValue)")
  }

  private var state: FirstRealAppCardState? {
    defaults.string(forKey: .firstRealAppCardState).flatMap(FirstRealAppCardState.init(rawValue:))
  }

  private func write(_ state: FirstRealAppCardState) {
    defaults.set(state.rawValue, forKey: .firstRealAppCardState)
  }

  // MARK: - Activation

  /// Dwell, then re-verify. An activation alone is not "the user opened this" —
  /// ⌘-Tab passes through several apps — and the app in front three seconds
  /// later is the one the copy has to name.
  func handleActivation(bundleIdentifier: String?, appName: String?) {
    dwell?.cancel()
    dwell = nil
    guard !cardIsLive, state == .pending else { return }
    guard let bundleIdentifier, !bundleIdentifier.isEmpty else { return }
    // Cheap pre-filter on the activation itself, so switching to Omi or to the
    // Dock does not arm a three-second timer whose only job is to be discarded.
    guard evaluate(bundleIdentifier: bundleIdentifier, appName: appName).isFire else { return }

    dwell = scheduler.schedule(after: FirstRealAppCardPolicy.requiredDwell) { [weak self] in
      guard let self else { return }
      self.dwell = nil
      let frontmost = self.frontmostApp()
      // Re-verified against what is actually in front now, not against what
      // the activation claimed: a card naming an app the user already left is
      // worse than no card.
      guard frontmost.bundleIdentifier == bundleIdentifier else { return }
      self.fireIfEarned(bundleIdentifier: bundleIdentifier, appName: frontmost.localizedName ?? appName)
    }
  }

  private func evaluate(bundleIdentifier: String?, appName: String?) -> FirstRealAppCardPolicy.Decision {
    let environment = environment()
    return FirstRealAppCardPolicy.decide(
      FirstRealAppCardPolicy.Input(
        state: state,
        frontmostBundleIdentifier: bundleIdentifier,
        frontmostAppName: appName,
        omiBundleIdentifier: environment.omiBundleIdentifier,
        isOnboardingComplete: environment.isOnboardingComplete,
        isSignedIn: environment.ownerID != nil
      )
    )
  }

  private func fireIfEarned(bundleIdentifier: String, appName: String?) {
    let environment = environment()
    let decision = evaluate(bundleIdentifier: bundleIdentifier, appName: appName)
    guard decision.isFire, let appName, let ownerID = environment.ownerID else {
      if let reason = decision.suppression {
        log("FirstRealAppCardCoordinator: not firing (\(reason.rawValue))")
      }
      return
    }

    // Consume before delivering. A card that reaches the screen and a card that
    // the bar refuses are both "this install's one shot", and re-arming on a
    // refusal is how a one-shot becomes a card the user sees on every app
    // switch until it happens to land.
    write(.consumed)
    cardIsLive = true

    presenter(
      ownerID,
      FirstRealAppCardPolicy.title(appName: appName),
      FirstRealAppCardPolicy.body(pttChordTokens: environment.pttChordTokens)
    )
    AnalyticsManager.shared.firstRealAppCard(phase: .shown)
    // The card says "Hold ⌥ and ask me anything". Have the microphone running
    // before they do, so the first hold is not the one that gets discarded.
    warmCapture()

    stopObservingPTT = pttObserver { [weak self] in
      self?.handlePushToTalkStarted()
    }
    timeout = scheduler.schedule(after: FirstRealAppCardPolicy.visibleDuration) { [weak self] in
      self?.timeout = nil
      self?.retireCard(phase: .timedOut, dismissKind: .timeout)
    }

    if let activationObserver {
      // Its job is done for the life of this install.
      NSWorkspace.shared.notificationCenter.removeObserver(activationObserver)
      self.activationObserver = nil
    }
  }

  // MARK: - Exits

  /// The user tapped the card. The bar has already dismissed it and recorded
  /// its own click event; this opens the chat with the question waiting in the
  /// composer, focused and unsent.
  func handleCardTapped(prompt: String) {
    retireCard(phase: .tapped, dismissKind: nil)
    openChat(prompt)
  }

  /// The user closed the card with ✕.
  func handleCardDismissed() {
    retireCard(phase: .dismissed, dismissKind: nil)
  }

  /// The user did the thing the card asked for. Take the card down so the notch
  /// is not narrating over a live voice turn.
  private func handlePushToTalkStarted() {
    retireCard(phase: .pttAfterCard, dismissKind: .user)
  }

  /// One terminal phase per card, then every clock and observer this card owns
  /// is torn down. `dismissKind` is nil when the bar has already taken the card
  /// down itself (tap and ✕ both route through `dismissCurrentNotification`).
  private func retireCard(
    phase: FirstRealAppCardTelemetry.Phase?,
    dismissKind: NotificationDismissalKind?
  ) {
    guard cardIsLive else { return }
    cardIsLive = false
    timeout?.cancel()
    timeout = nil
    stopObservingPTT?()
    stopObservingPTT = nil
    if let dismissKind { dismisser(dismissKind) }
    if let phase { AnalyticsManager.shared.firstRealAppCard(phase: phase) }
  }
}
