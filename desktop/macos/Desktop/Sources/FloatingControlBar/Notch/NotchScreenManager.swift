import AppKit
import SwiftUI

/// Owns one notch panel per display. The notch is visible on every screen but
/// only the panel under the mouse ever expands. Also the single auto-close
/// authority: pointer monitors are installed only while a panel is open, so
/// idle CPU stays at ~0%.
@MainActor
final class NotchScreenManager {
  private struct Panel {
    let window: NotchWindow
    let vm: NotchViewModel
  }

  private var panels: [CGDirectDisplayID: Panel] = [:]
  private var screenObserver: NSObjectProtocol?
  private var appActivationObserver: NSObjectProtocol?
  private var rebuildTask: Task<Void, Never>?
  private var mouseMonitors: [Any] = []
  /// Per-panel timestamp of when the pointer first left its close zone; reset
  /// whenever the pointer is back inside (or aiming toward it).
  private var outsideSince: [CGDirectDisplayID: Date] = [:]
  /// Previous pointer sample per panel, so we can tell whether the pointer is
  /// moving TOWARD the panel (intent) versus drifting away.
  private var lastPointer: [CGDirectDisplayID: CGPoint] = [:]
  /// Fires a delayed pointerMoved so a stationary-while-outside pointer still
  /// triggers the close. One pending task at a time.
  private var outsideRecheckTask: Task<Void, Never>?

  /// Moving the pointer off the panel doesn't close it quickly — the panel is
  /// "sticky, but dismissable" (click outside or Esc). This dwell is the
  /// safety net for "the user walked away entirely".
  private static let outsideGrace: TimeInterval = 10

  private weak var barState: FloatingControlBarState?
  private weak var chatProvider: ChatProvider?

  /// Lock-free-enough throttle usable from the monitor callback thread.
  private final class PointerThrottle: @unchecked Sendable {
    private let lock = NSLock()
    private var last = Date.distantPast
    func shouldFire() -> Bool {
      lock.withLock {
        guard Date.now.timeIntervalSince(last) > 0.08 else { return false }
        last = .now
        return true
      }
    }
  }

  /// System agents that present permission/auth dialogs. While one of these is
  /// frontmost, panels drop below dialog level so the prompt is never hidden
  /// behind the notch. Lowercased so the membership check can't be broken by a
  /// casing mismatch.
  private nonisolated static let systemDialogAgents: Set<String> = [
    "com.apple.usernotificationcenter",  // TCC permission alerts
    "com.apple.securityagent",  // keychain / authorization
    "com.apple.coreservices.uiagent",  // gatekeeper & consent prompts
    "com.apple.corelocationagent",
    "com.apple.universalaccessauthwarn",  // accessibility "control this computer" prompt
  ]

  func start(barState: FloatingControlBarState, chatProvider: ChatProvider) {
    self.barState = barState
    self.chatProvider = chatProvider
    rebuild()

    screenObserver = NotificationCenter.default.addObserver(
      forName: NSApplication.didChangeScreenParametersNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      Task { @MainActor in self?.scheduleRebuild() }
    }

    appActivationObserver = NSWorkspace.shared.notificationCenter.addObserver(
      forName: NSWorkspace.didActivateApplicationNotification,
      object: nil,
      queue: .main
    ) { [weak self] note in
      let bundleID = (note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication)?
        .bundleIdentifier
      let yields = bundleID.map { Self.systemDialogAgents.contains($0.lowercased()) } ?? false
      Task { @MainActor in
        guard let self else { return }
        for (_, panel) in self.panels {
          panel.window.setYieldsToSystemDialog(yields)
        }
      }
    }
  }

  func stop() {
    rebuildTask?.cancel()
    outsideRecheckTask?.cancel()
    if let screenObserver {
      NotificationCenter.default.removeObserver(screenObserver)
    }
    if let appActivationObserver {
      NSWorkspace.shared.notificationCenter.removeObserver(appActivationObserver)
    }
    removeMouseMonitors()
    for (_, panel) in panels {
      panel.vm.cancelHoverTasks()
      panel.window.orderOut(nil)
    }
    panels.removeAll()
  }

  /// Opens the panel on the screen containing the mouse (else the main
  /// display). Used by the Ask-Omi hotkey and notification click-through.
  func openPrimary(tab: NotchTab = .chat) {
    let pointer = NSEvent.mouseLocation
    let target =
      panels.values.first { $0.vm.screenFrame.contains(pointer) }
      ?? panels[CGMainDisplayID()]
      ?? panels.values.first
    guard let target else { return }
    withAnimation(NotchAnimation.open) { target.vm.open(tab: tab) }
  }

  /// Opens the agents tab drilled into a specific agent (timeline click,
  /// agent-completion click-through).
  func openAgent(pillID: UUID) {
    let pointer = NSEvent.mouseLocation
    let target =
      panels.values.first { $0.vm.screenFrame.contains(pointer) }
      ?? panels[CGMainDisplayID()]
      ?? panels.values.first
    guard let target else { return }
    target.vm.openAgentPillID = pillID
    withAnimation(NotchAnimation.open) { target.vm.open(tab: .agents) }
  }

  func closeAll() {
    for (_, panel) in panels where panel.vm.state == .open {
      withAnimation(NotchAnimation.close) { panel.vm.close() }
    }
  }

  var hasOpenPanel: Bool {
    panels.values.contains { $0.vm.state == .open }
  }

  /// True while an open panel's composer (or any text field inside it) holds
  /// keyboard focus. Automation's proxy for "the conversation is focused".
  var anyPanelKeyboardFocused: Bool {
    panels.values.contains { $0.window.firstResponder is NSTextView }
  }

  /// The frame of the panel `openPrimary` would target. nil before any panel exists.
  var primaryPanelFrame: NSRect? {
    let pointer = NSEvent.mouseLocation
    let target =
      panels.values.first { $0.vm.screenFrame.contains(pointer) }
      ?? panels[CGMainDisplayID()]
      ?? panels.values.first
    return target?.window.frame
  }

  /// Order every panel back on screen (show / clearing snooze).
  func showAll() {
    for (_, panel) in panels { panel.window.orderFrontRegardless() }
  }

  /// Order every panel off screen (hide / snooze / disable).
  func hideAll() {
    for (_, panel) in panels {
      panel.vm.close()
      panel.window.orderOut(nil)
    }
  }

  /// Clear the agents-tab drill-in on any panel showing this pill, so a
  /// dismissed pill doesn't leave the agents tab pointed at a removed agent.
  func clearAgentDrillIn(pillID: UUID) {
    for (_, panel) in panels where panel.vm.openAgentPillID == pillID {
      panel.vm.openAgentPillID = nil
    }
  }

  // MARK: - Panel lifecycle

  /// Display hot-plug/sleep fires bursts of change notifications; settle first.
  private func scheduleRebuild() {
    rebuildTask?.cancel()
    rebuildTask = Task { [weak self] in
      try? await Task.sleep(for: .seconds(0.5))
      guard !Task.isCancelled else { return }
      self?.rebuild()
    }
  }

  private func rebuild() {
    var seen: Set<CGDirectDisplayID> = []

    for screen in NSScreen.screens {
      let id = screen.omiDisplayID
      seen.insert(id)
      if let panel = panels[id] {
        panel.vm.refresh(for: screen)
      } else {
        panels[id] = makePanel(for: screen)
      }
    }

    for (id, panel) in panels where !seen.contains(id) {
      panel.vm.cancelHoverTasks()
      panel.window.orderOut(nil)
      panels.removeValue(forKey: id)
      outsideSince.removeValue(forKey: id)
      lastPointer.removeValue(forKey: id)
    }
  }

  private func makePanel(for screen: NSScreen) -> Panel {
    let vm = NotchViewModel(screen: screen)
    let window = NotchWindow(
      contentRect: .zero,
      styleMask: [.borderless, .nonactivatingPanel, .utilityWindow, .hudWindow],
      backing: .buffered,
      defer: false
    )
    let root = NotchView(vm: vm, chatProvider: chatProvider)
      .environmentObject(barState ?? FloatingControlBarState())
    window.contentView = NotchHostingView(rootView: AnyView(root))
    window.onEscape = { [weak vm] in
      guard let vm, vm.state == .open else { return }
      withAnimation(NotchAnimation.close) { vm.close() }
    }
    vm.attach(window: window)
    vm.onStateChange = { [weak self] in self?.updateMouseMonitors() }
    window.orderFrontRegardless()
    return Panel(window: window, vm: vm)
  }

  // MARK: - Pointer tracking (auto-close authority)

  /// The pointer monitors drive ONE thing — auto-close — which only matters
  /// while a panel is open. Hover-to-open is handled by SwiftUI, so closed =
  /// no mouse tracking. Installed on the first open, removed when the last
  /// panel closes (via each view-model's onStateChange).
  private func installMouseMonitors() {
    guard mouseMonitors.isEmpty else { return }
    // SwiftUI onHover can miss exit events during animated resizes, so the
    // real pointer position is the authoritative close signal. Throttle before
    // the actor hop — this fires for every pointer move on screen.
    let throttle = PointerThrottle()
    if let global = NSEvent.addGlobalMonitorForEvents(
      matching: .mouseMoved,
      handler: { [weak self] _ in
        guard throttle.shouldFire() else { return }
        Task { @MainActor in self?.pointerMoved() }
      })
    {
      mouseMonitors.append(global)
    }
    if let local = NSEvent.addLocalMonitorForEvents(
      matching: .mouseMoved,
      handler: { [weak self] event in
        // Hop off the handler stack: closing the last panel removes these
        // monitors synchronously, and removing a monitor from inside its own
        // handler is unsafe.
        Task { @MainActor in self?.pointerMoved() }
        return event
      })
    {
      mouseMonitors.append(local)
    }
    // Click-away dismiss: a click landing in another app / the desktop arrives
    // as a GLOBAL mouseDown (clicks inside the panel are local and never reach
    // this). Closes immediately — the deliberate counterpart to the long
    // mouse-leave grace.
    if let clicks = NSEvent.addGlobalMonitorForEvents(
      matching: [.leftMouseDown, .rightMouseDown],
      handler: { [weak self] _ in
        Task { @MainActor in self?.pointerClickedOutside() }
      })
    {
      mouseMonitors.append(clicks)
    }
  }

  private func removeMouseMonitors() {
    for monitor in mouseMonitors { NSEvent.removeMonitor(monitor) }
    mouseMonitors.removeAll()
    outsideRecheckTask?.cancel()
    outsideSince.removeAll()
    lastPointer.removeAll()
  }

  /// Keep the monitors installed exactly while at least one panel is open, and
  /// hand the keyboard to whichever panel is open (composer typing) —
  /// releasing it back to the user's app when all panels close.
  private func updateMouseMonitors() {
    if panels.values.contains(where: { $0.vm.state == .open }) {
      installMouseMonitors()
    } else {
      removeMouseMonitors()
    }
    for panel in panels.values {
      panel.window.keyboardCaptureAllowed = (panel.vm.state == .open)
    }
  }

  /// The single auto-close authority. The close zone is the SOLID region from
  /// the notch body's top down to the floating tray's bottom (body ∪ tray,
  /// generously inset) — so moving onto the composer never reads as "left the
  /// panel". While the pointer is aiming toward that zone, the grace dwell is
  /// held; only a clear move away arms the close.
  private func pointerMoved() {
    let pointer = NSEvent.mouseLocation
    let now = Date.now
    var awaitingClose = false

    for (id, panel) in panels where panel.vm.state == .open {
      let zone = Self.closeZone(body: panel.vm.visibleRect(open: true), tray: panel.vm.trayRect(open: true))
      if zone.contains(pointer) {
        outsideSince[id] = nil
        lastPointer[id] = pointer
        continue
      }

      let prev = lastPointer[id] ?? pointer
      lastPointer[id] = pointer

      // Intent: still heading toward the panel -> hold the close, but keep
      // re-checking since the pointer may stop.
      if Self.isAiming(toward: zone, from: prev, to: pointer) {
        outsideSince[id] = nil
        awaitingClose = true
        continue
      }

      let since = outsideSince[id] ?? now
      outsideSince[id] = since

      if now.timeIntervalSince(since) >= Self.outsideGrace, canAutoClose(panel) {
        outsideSince[id] = nil
        withAnimation(NotchAnimation.close) { panel.vm.close() }
      } else {
        // Dwell not yet elapsed, or a guard is holding it open; the pointer
        // may now be stationary, so re-check on a timer.
        awaitingClose = true
      }
    }

    if awaitingClose {
      scheduleOutsideRecheck()
    } else {
      outsideRecheckTask?.cancel()
    }
  }

  /// A click outside every open panel's zone dismisses it (respecting the same
  /// guards as the hover close — never mid-response or mid-voice).
  private func pointerClickedOutside() {
    let pointer = NSEvent.mouseLocation
    for (id, panel) in panels where panel.vm.state == .open {
      // Tighter than the hover zone: a deliberate click just needs to be
      // clearly off the panel, not the generous "still aiming" margin.
      let zone = panel.vm.visibleRect(open: true)
        .union(panel.vm.trayRect(open: true))
        .insetBy(dx: -8, dy: -8)
      guard !zone.contains(pointer), canAutoClose(panel, allowPressedButton: true) else { continue }
      outsideSince[id] = nil
      withAnimation(NotchAnimation.close) { panel.vm.close() }
    }
  }

  /// The pointer can stop moving while outside a panel; without a timed
  /// re-check the dwell (or a lifted guard) would never be observed.
  private func scheduleOutsideRecheck() {
    outsideRecheckTask?.cancel()
    outsideRecheckTask = Task { [weak self] in
      try? await Task.sleep(for: .seconds(0.25))
      guard !Task.isCancelled else { return }
      self?.pointerMoved()
    }
  }

  /// Pointer-tracking close is allowed only when the view-model's own grace
  /// (state / holdOpen / 0.6s-since-open) passes AND nothing here demands the
  /// panel stay up: an in-flight response, an active voice turn, or a held
  /// mouse button (drag / text selection in progress).
  private func canAutoClose(_ panel: Panel, allowPressedButton: Bool = false) -> Bool {
    guard panel.vm.canAutoClose else { return false }
    if chatProvider?.isSending == true { return false }
    if barState?.isVoicePresentationActive == true { return false }
    // The pressed-button guard protects the HOVER path from closing mid-drag
    // or mid-text-selection. A deliberate click-away is itself a press, so
    // that path opts out — else it could never close.
    if !allowPressedButton, NSEvent.pressedMouseButtons != 0 { return false }
    return true
  }

  // MARK: - Pure zone math (tested)

  /// The solid body∪tray region, generously inset so the body↔tray gap and
  /// small overshoots stay "inside".
  static func closeZone(body: CGRect, tray: CGRect) -> CGRect {
    body.union(tray).insetBy(dx: -48, dy: -44)
  }

  /// Apple's "menu aim" intent, in velocity-cone form: the pointer counts as
  /// aiming when it moved closer to the zone since the last sample AND its
  /// movement points into the zone (within ~60° of straight-at-it). A
  /// stationary or receding pointer is not aiming, so the dwell can run.
  static func isAiming(toward zone: CGRect, from prev: CGPoint, to cur: CGPoint) -> Bool {
    func distance(_ p: CGPoint) -> CGFloat {
      let dx = max(zone.minX - p.x, 0, p.x - zone.maxX)
      let dy = max(zone.minY - p.y, 0, p.y - zone.maxY)
      return (dx * dx + dy * dy).squareRoot()
    }
    guard distance(cur) < distance(prev) - 0.5 else { return false }
    let move = CGVector(dx: cur.x - prev.x, dy: cur.y - prev.y)
    let toZone = CGVector(dx: zone.midX - prev.x, dy: zone.midY - prev.y)
    let moveMag = (move.dx * move.dx + move.dy * move.dy).squareRoot()
    let zoneMag = (toZone.dx * toZone.dx + toZone.dy * toZone.dy).squareRoot()
    guard moveMag > 0.5, zoneMag > 0.5 else { return false }
    let cosine = (move.dx * toZone.dx + move.dy * toZone.dy) / (moveMag * zoneMag)
    return cosine > 0.5
  }
}
