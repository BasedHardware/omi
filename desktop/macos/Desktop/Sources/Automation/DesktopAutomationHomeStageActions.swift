//
//  DesktopAutomationHomeStageActions.swift — the bridge's five Home-stage actions.
//
//  Every one of these drives the Home stage without touching the cursor: each posts the notification
//  the stage's own view observes, which runs the exact function the on-screen control runs. That is
//  the whole contract — a bridge action is a second caller of production code, never a second
//  implementation of it.
//
//  **They are together in one file because they share a failure mode, not just a prefix.** The stage
//  is rendered by one view; when a shell stops mounting that view, every action here posts into an
//  empty room. Four of them were re-hosted on the query-shell Home (`QueryShellHome`) once that
//  happened; `home_connect_toggle` could not be, and refuses instead. Reading that reasoning as one
//  page is the point — split across a 4,000-line registry it is five unrelated-looking closures, and
//  the one that had gone inert stayed inert for exactly that reason.
//
//  Registered from `DesktopAutomationActionRegistry.registerBuiltins()`, the same way
//  `registerOpenOmiShortcutActionsForQA()` is.
//

import Foundation

extension DesktopAutomationActionRegistry {

  /// Drive the Home stage (inline chat / connect tray) without the cursor.
  func registerHomeStageActions() {
    register(
      name: "home_open_chat",
      summary: "Open the inline chat on Home (same path as clicking the ask bar)"
    ) { _ in
      NotificationCenter.default.post(name: .homeStageOpenChat, object: nil)
      return nil
    }

    // The one `home_*` action with no counterpart on the query-shell Home. The other four were
    // re-hosted there (`QueryShellHome`) because that surface still has the thing they act on — a
    // chat to open, a panel to close, a question to send, a file to stage. It has no Connect tray
    // and no control that opens one: connectors and export destinations moved to the Apps page,
    // which the bar reaches with its own pill and the bridge reaches with `navigate apps`.
    //
    // So this refuses rather than pretending. Re-pointing it at the Apps page would keep the
    // "toggle" name over a different destination, and a flow asserting a Connect tray would then
    // watch the wrong surface and call it a pass — the same lie in new clothes.
    register(
      name: "home_connect_toggle",
      summary:
        "Toggle the Connect tray on the Home stage (same path as the ask-bar Connect button). "
        + "Errors on shells whose Home has no stage; connectors live on the Apps page there."
    ) { _ in
      // `homeMode` is the stage's own answer to "is there a Connect tray here". It is written only
      // by the view that renders the stage. `DashboardPage` was that view and no longer exists, so
      // this is now always nil and the action always refuses — rather than answering "ok" and doing
      // nothing, which is what it did from the query-shell Home landing until this guard.
      guard DesktopAutomationStateStore.shared.current().homeMode != nil else {
        return [
          "error": "no Home stage on this shell, so there is no Connect tray to toggle — "
            + "connectors and export destinations live on the Apps page (navigate apps)"
        ]
      }
      NotificationCenter.default.post(name: .homeStageToggleConnect, object: nil)
      return nil
    }

    register(
      name: "home_close_panel",
      summary: "Collapse Home back to its resting surface (same as Esc / the close buttons)"
    ) { _ in
      NotificationCenter.default.post(name: .homeStageClose, object: nil)
      return nil
    }

    register(
      name: "home_ask",
      summary: "Send a query through the Home ask bar (opens the inline chat and sends)",
      params: ["query"]
    ) { params in
      let query = (params["query"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !query.isEmpty else { return ["error": "missing 'query'"] }
      NotificationCenter.default.post(
        name: .homeStageAsk, object: nil, userInfo: ["query": query])
      return ["sent": query]
    }

    register(
      name: "home_attach",
      summary: "Stage a file in the Home ask bar (same wiring as the paperclip/drag-drop)",
      params: ["path"]
    ) { params in
      let path = (params["path"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
      guard !path.isEmpty, FileManager.default.fileExists(atPath: path) else {
        return ["error": "missing or nonexistent 'path'"]
      }
      NotificationCenter.default.post(
        name: .homeStageAttach, object: nil, userInfo: ["path": path])
      return ["staged": path]
    }
  }
}
