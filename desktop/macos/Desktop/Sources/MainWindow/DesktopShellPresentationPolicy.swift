enum DesktopShellPresentationPolicy {
  static func usesChatFirst(_ useLegacyHomeDesign: Bool, _ capabilityVariant: ChatFirstShellVariant) -> Bool {
    guard !useLegacyHomeDesign else { return false }
    if case .chatFirst = capabilityVariant { return true }
    return false
  }

  /// The floating "Try asking" popup belongs to the legacy shell. Chat-first owns its starter
  /// prompts inside the main chat and must never expose the notch as a primary text-entry surface.
  static func usesLegacyPostOnboardingPopup(
    _ useLegacyHomeDesign: Bool,
    _ capabilityVariant: ChatFirstShellVariant
  ) -> Bool {
    !usesChatFirst(useLegacyHomeDesign, capabilityVariant)
  }
}

enum HomeDesignPresentation: Equatable {
  case queryShell
  case redesignedHub
  case oldestLegacy

  static func resolve(
    useLegacyHomeDesign: Bool,
    useOldestHomeDesign: Bool,
    forceModernPresentation: Bool
  ) -> Self {
    guard !forceModernPresentation, useLegacyHomeDesign else { return .queryShell }
    return useOldestHomeDesign ? .oldestLegacy : .redesignedHub
  }

  static func queryShellOwnsItsPanels(
    useLegacyHomeDesign: Bool,
    forceModernPresentation: Bool
  ) -> Bool {
    resolve(
      useLegacyHomeDesign: useLegacyHomeDesign,
      useOldestHomeDesign: false,
      forceModernPresentation: forceModernPresentation
    ) == .queryShell
  }
}

@MainActor
enum FloatingPrimaryTextInputRouting {
  private(set) static var routesToMainApp = false

  static func configure(routesToMainApp: Bool) {
    self.routesToMainApp = routesToMainApp
  }

  static func shouldRouteAgentExitToMainApp(hasMainConversation: Bool) -> Bool {
    routesToMainApp && !hasMainConversation
  }
}

/// Whether the Home stage — `HomeStageMode`'s hub / chat / connect — is mounted at all, and therefore
/// whether `DesktopAutomationSnapshot.homeMode` has anything true to say.
///
/// **`DashboardPage` renders that stage and is its only writer.** The shell must never synthesize a
/// value for it. This began as an inline `(priorHomeMode ?? "hub")` guarded on "not chat-first, not
/// legacy, on the Dashboard tab" — which named `DashboardPage` exactly, on the day it was written.
/// Home then became `QueryShellHome`, a surface with no stage at all, and that same guard went on
/// answering `hub` forever.
///
/// **A fabricated reading is worse than a missing one**, because `hub` is *plausible*. Nothing looks
/// broken: a flow waiting for `chat` waits for a transition that can never arrive, a flow asserting
/// `hub` passes without touching the app, and an agent reading `/state` draws a confident wrong
/// conclusion about a surface that is not on screen. `nil` says the one true thing — this shell has
/// no stage — and every reader already handles it, because legacy Home has always reported `nil`.
enum HomeStageAutomationPolicy {

  /// The last mode `DashboardPage` published, or `nil` when nothing is rendering the stage. Never a
  /// default and never a guess: the shell's job here is to carry the owner's value or say there is
  /// no owner.
  static func reportedHomeMode(
    usesChatFirstShell: Bool,
    chatFirstRoute: ChatFirstRoute?,
    lastPublishedMode: String?
  ) -> String? {
    guard usesChatFirstShell, let chatFirstRoute, mountsHomeStage(chatFirstRoute) else { return nil }
    return lastPublishedMode
  }

  /// The routes that mount `DashboardPage`, the only view that renders the stage.
  ///
  /// The legacy shell has no entry here on purpose, and that is the whole correction: its Home is
  /// `QueryShellHome`, which renders the query surface, and the one branch that still mounts
  /// `DashboardPage` there requires `useLegacyHomeDesign` — which routes to `legacyHome`. No stage
  /// either way.
  ///
  /// An exhaustive `switch` rather than a `default`, so a route added later has to state its answer
  /// instead of inheriting "reports a stage mode" from a fallthrough.
  static func mountsHomeStage(_ route: ChatFirstRoute) -> Bool {
    switch route {
    case .chat:
      return true
    case .more(let page):
      return page == .dashboard
    case .conversations, .tasks, .goals, .memories:
      return false
    }
  }
}
