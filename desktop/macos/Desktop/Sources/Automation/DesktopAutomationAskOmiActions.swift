//
//  DesktopAutomationAskOmiActions.swift — `open_ask_omi` reports the chat-first composer.
//
//  Typed Ask Omi is the main-window composer (`openMainAppChat` / `QueryShellHome`), not the
//  retired notch composer. This action is a second caller of that path: it selects Chat and
//  posts `.homeStageOpenChat` (the same caret claim `home_open_chat` uses). It never calls
//  `openMainAppWindow()` / `revealForUser()`, so a quiet automation harness stays quiet instead
//  of being activated and then timing out on `showingAIConversation`.
//
//  Registered from `DesktopAutomationActionRegistry.registerBuiltins()`.
//

import AppKit
import Foundation

/// Snapshot and action answers for "is typed Ask Omi presented / focused".
@MainActor
enum OpenAskOmiAutomation {
  static let targetName = "main_chat"

  static func isComposerPresented(
    _ navigation: ChatFirstShellNavigation = .shared
  ) -> Bool {
    // `route` is the navigation command; `visibleRoute` is the mounted
    // destination's acknowledgement (`markRouteVisible` from `onAppear`). On a
    // cold shell or a switch from another route, `selectPrimary` sets `route`
    // before SwiftUI mounts Chat, so reporting on `route` would claim an open
    // composer that is not on screen yet — the same lie this PR fixes (#13201).
    navigation.visibleRoute == .chat
  }

  static func isComposerFocused(
    _ navigation: ChatFirstShellNavigation = .shared
  ) -> Bool {
    guard isComposerPresented(navigation) else { return false }
    return shellWindowIfAppRunning()?.firstResponder is NSTextView
  }

  /// Select Chat and claim the query-shell caret. Does not activate the app or exit quiet mode.
  static func requestComposer(
    navigation: ChatFirstShellNavigation = .shared,
    ensureWindow: Bool = true
  ) {
    navigation.selectPrimary(.chat, origin: .chatDeeplink)
    NotificationCenter.default.post(name: .homeStageOpenChat, object: nil)
    // A headless XCTest host has no NSApplication. Do not create one
    // (`NSApplication.shared`) and do not ask AppDelegate to open a window.
    if ensureWindow, runningApplication() != nil, shellWindowIfAppRunning() == nil {
      AppDelegate.openMainWindow?()
    }
  }

  /// `NSApp` is an IUO and is nil in a headless XCTest host. Never create
  /// `NSApplication.shared` from here — that has AppKit side effects in tests.
  fileprivate static func shellWindowIfAppRunning() -> NSWindow? {
    guard runningApplication() != nil else { return nil }
    return ShellSummon.shellWindow()
  }

  fileprivate static func runningApplication() -> NSApplication? {
    let application: NSApplication? = NSApp
    return application
  }

  static func detail(
    wait: Bool,
    presentation: DesktopAutomationUIPresentationMode,
    presented: Bool,
    focused: Bool,
    openMs: String? = nil,
    focusMs: String? = nil,
    elapsedMs: String? = nil
  ) -> [String: String] {
    var detail: [String: String] = [
      "target": targetName,
      "presentation": presentation.rawValue,
      "focused": focused ? "true" : "false",
    ]
    if !wait {
      detail["triggered"] = "true"
    }
    if let openMs {
      detail["openMs"] = openMs
    }
    if let focusMs {
      detail["focusMs"] = focusMs
    }
    if let elapsedMs {
      detail["elapsedMs"] = elapsedMs
    }
    if wait, !presented {
      detail["error"] = "main_chat_composer_not_presented"
    }
    return detail
  }
}

extension DesktopAutomationActionRegistry {

  func registerOpenAskOmiActions() {
    register(
      name: "open_ask_omi",
      effects: [.localState, .networkOrModel, .remoteWrite],
      summary:
        "Open the chat-first main-window composer (typed Ask Omi) and return open/focus timing. "
        + "Does not call revealForUser, so quiet automation presentation stays quiet: the action "
        + "returns target=main_chat and presentation=quiet with focused=false rather than timing out "
        + "on the retired notch composer.",
      params: ["reset", "wait"],
      category: "chat",
      surfaces: ["main_chat"]
    ) { params in
      let reset = boolParam(params["reset"], default: false)
      let wait = boolParam(params["wait"], default: true)
      if reset, let provider = ChatProvider.mainInstance {
        if let error = await provider.automationResetMainChatForHarness() {
          return ["error": error]
        }
      }
      return await openAskOmiForAutomation(wait: wait)
    }
  }

  /// The close half of the Ask Omi pair, kept next to the open action so the two
  /// cannot drift apart again (`open_ask_omi` opens `main_chat`, this closes the
  /// floating panel and discloses the resting main-chat surface).
  func registerCloseAskOmiActions() {
    register(
      name: "close_ask_omi",
      effects: [.localState],
      summary:
        "Close the floating Ask Omi input panel if it is open; the chat-first main-window "
        + "composer is the resting Chat surface, so when it is presented the result reports "
        + "mainChatPresented=true / mainChatClosed=false instead of implying a floating-bar-only close",
      params: ["wait"]
    ) { params in
      let wait = boolParam(params["wait"], default: true)
      var result = await FloatingControlBarManager.shared.closeAskOmiForAutomation(wait: wait)
      // `open_ask_omi` opens the chat-first main-window composer. That composer
      // is the resting Chat destination (INV-NAV-1): it has no close, so a
      // paired flow must not read a floating-bar-only result as "Ask Omi is
      // closed" while the main-chat surface is presented. Name it instead.
      if OpenAskOmiAutomation.isComposerPresented() {
        result["mainChatPresented"] = "true"
        result["mainChatClosed"] = "false"
      }
      return result
    }
  }
}

@MainActor
private func openAskOmiForAutomation(wait: Bool) async -> [String: String] {
  let start = ContinuousClock.now
  let presentation = DesktopAutomationWindowPresentation.currentMode
  OpenAskOmiAutomation.requestComposer()

  if !wait {
    return OpenAskOmiAutomation.detail(
      wait: false,
      presentation: presentation,
      presented: OpenAskOmiAutomation.isComposerPresented(),
      focused: OpenAskOmiAutomation.isComposerFocused()
    )
  }

  // `selectPrimary` completes the navigation command, not the mount: Chat is
  // on screen only after the destination acknowledges via `markRouteVisible`.
  // Wait (bounded) for that acknowledgement before recording the open result,
  // so `openMs` never measures a composer that is not actually open.
  let presentedImmediately = OpenAskOmiAutomation.isComposerPresented()
  let openMs: String
  if presentedImmediately {
    openMs = start.duration(to: .now).askOmiMillisecondsString
  } else {
    let mounted = await waitForAskOmiAutomationCondition {
      OpenAskOmiAutomation.isComposerPresented()
    }
    openMs = mounted ?? "timeout"
  }
  let presented = OpenAskOmiAutomation.isComposerPresented()
  let quiet = presentation == .quiet
  let canWaitForFocus = !quiet && OpenAskOmiAutomation.shellWindowIfAppRunning() != nil
  if !canWaitForFocus {
    return OpenAskOmiAutomation.detail(
      wait: true,
      presentation: presentation,
      presented: presented,
      focused: OpenAskOmiAutomation.isComposerFocused(),
      openMs: openMs,
      elapsedMs: start.duration(to: .now).askOmiMillisecondsString
    )
  }

  let focusMs = await waitForAskOmiAutomationCondition {
    OpenAskOmiAutomation.isComposerFocused()
  }
  return OpenAskOmiAutomation.detail(
    wait: true,
    presentation: presentation,
    presented: OpenAskOmiAutomation.isComposerPresented(),
    focused: OpenAskOmiAutomation.isComposerFocused(),
    openMs: openMs,
    focusMs: focusMs ?? "timeout",
    elapsedMs: start.duration(to: .now).askOmiMillisecondsString
  )
}

@MainActor
private func waitForAskOmiAutomationCondition(_ condition: @MainActor @escaping () -> Bool) async -> String? {
  let start = ContinuousClock.now
  while start.duration(to: .now) < .milliseconds(500) {
    if condition() {
      return start.duration(to: .now).askOmiMillisecondsString
    }
    try? await Task.sleep(for: .milliseconds(5))
  }
  return nil
}

extension Duration {
  fileprivate var askOmiMillisecondsString: String {
    let components = self.components
    let milliseconds =
      Double(components.seconds) * 1000
      + Double(components.attoseconds) / 1_000_000_000_000_000
    return String(format: "%.1f", milliseconds)
  }
}
