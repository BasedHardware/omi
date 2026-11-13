import AppKit

/// Non-production probes for passive presentation through the real AppKit owners.
/// Notification chrome is rendered directly rather than sending an account notification.
extension DesktopAutomationActionRegistry {
  func registerPassiveWindowActions() {
    register(
      name: "probe_passive_window",
      effects: [.localState, .networkOrModel, .remoteWrite],
      summary: "Exercise local window presentation and report focus/visibility (non-production QA)",
      params: ["event"]
    ) { params in
      let manager = FloatingControlBarManager.shared
      let event = params["event"] ?? "snapshot"
      if event == "prepare", manager.window == nil {
        manager.window = FloatingControlBarWindow(
          contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
      }
      guard let window = manager.window else { return ["error": "prepare the local bar first"] }
      let frontmostBefore = NSWorkspace.shared.frontmostApplication?.processIdentifier
      switch event {
      case "prepare":
        manager.isEnabled = true
        manager.snoozedUntil = nil
        window.orderOut(nil)
      case "background": manager.present(.background, preferenceMutation: .preserve)
      case "background_input":
        window.state.showingAIConversation = true
        window.state.showingAIResponse = false
        manager.present(.background, preferenceMutation: .preserve)
      case "explicit": manager.present(.explicitUserAction, preferenceMutation: .preserve)
      case "temporary": manager.showTemporarily()
      case "snooze": manager.snooze(for: 3600)
      case "snooze_end": manager.endSnooze()
      case "disable": manager.hide()
      case "close": window.closeAIConversation(intent: .voiceHandoff)
      case "notification_surface":
        window.showNotification(
          FloatingBarNotification(
            ownerID: "local-window-probe", title: "Memory Saved", message: "Synthetic focus check",
            assistantId: "local-window-probe", kind: .memory), animated: false)
        window.orderFrontRegardless()
      case "dismiss_surface": window.dismissNotification(animated: false)
      case "recover_frame":
        guard let shell = ShellSummon.shellWindow() else { return ["error": "no shell window"] }
        shell.setFrameOrigin(NSPoint(x: -100_000, y: -100_000))
        ShellSummon.recoverStrandedFrameIfNeeded()
      case "snapshot": break
      default: return ["error": "unknown local window event"]
      }
      return [
        "event": event,
        "visible": String(window.isVisible),
        "key": String(window.isKeyWindow),
        "enabled": String(manager.isEnabled),
        "snoozed": String(manager.isSnoozed),
        "app_active": String(NSApp.isActive),
        "foreground_unchanged": String(frontmostBefore == NSWorkspace.shared.frontmostApplication?.processIdentifier),
        "shell_key": String(ShellSummon.shellWindow()?.isKeyWindow == true),
        "shell_on_screen": String(
          ShellSummon.shellWindow().map { shell in
            NSScreen.screens.contains { $0.visibleFrame.intersects(shell.frame) }
          } ?? false),
      ]
    }
  }
}
