import Cocoa

extension DesktopAutomationActionRegistry {
  /// Named-bundle QA for the elicitation card.
  ///
  /// A real permission needs a signed-in bundle and a live external agent, so
  /// the flow drives the production store directly instead. What it exercises
  /// is the part the card actually depends on: the queue transitions and the
  /// composer swapping shape around them. The answer path stops at the store's
  /// submit closure rather than reaching the kernel, which is why the flow
  /// asserts queue state rather than an agent's response.
  func registerElicitationActionsForQA() {
    #if DEBUG
      register(
        name: "elicitation_probe",
        summary:
          "Enqueue a synthetic pending elicitation so the composer swap can be asserted. DEBUG non-prod only.",
        params: ["dispatch_id", "mode", "allow_free_text"]
      ) { params in
        guard AppBuild.isNonProduction else {
          return ["error": "elicitation_probe is disabled on production bundles"]
        }
        let mode = params["mode"] ?? "permission"
        guard mode == "permission" || mode == "question" else {
          throw DesktopAutomationActionError.invalidParams("mode must be permission or question")
        }
        let ownerID = RuntimeOwnerIdentity.currentOwnerId() ?? "qa-owner"
        let payload: [String: Any] = [
          "dispatchId": params["dispatch_id"] ?? "qa-dispatch-1",
          "ownerId": ownerID,
          "sessionId": "qa-session",
          "mode": mode,
          "adapterId": "acp",
          "title": mode == "permission" ? "Claude Code needs permission" : "Claude Code is asking",
          "prompt": mode == "permission" ? "Write /tmp/qa-probe.txt" : "Which branch should I target?",
          "subject": mode == "permission" ? "/tmp/qa-probe.txt" : nil,
          "options": mode == "permission"
            ? [
              ["optionId": "allow", "label": "Allow", "effect": "allow_once"],
              ["optionId": "reject", "label": "Deny", "effect": "reject_once"],
            ]
            : [["optionId": "main", "label": "main", "effect": "choice"]],
          "allowsFreeText": (params["allow_free_text"] ?? "false") == "true",
          "createdAtMs": Date().timeIntervalSince1970 * 1000,
        ].compactMapValues { $0 }

        guard let elicitation = PendingElicitation(payload: payload) else {
          throw DesktopAutomationActionError.invalidParams("could not build a probe elicitation")
        }
        guard let provider = ChatProvider.mainInstance else {
          return ["error": "main ChatProvider not yet initialized"]
        }
        let store = provider.elicitations
        store.enqueue(elicitation)
        return [
          "queued": "\(store.waitingCount)",
          "current_dispatch_id": store.focused?.id ?? "",
        ]
      }

      register(
        name: "elicitation_snapshot",
        summary: "Report the pending elicitation queue as the composer sees it."
      ) { _ in
        guard let provider = ChatProvider.mainInstance else {
          return ["error": "main ChatProvider not yet initialized"]
        }
        let store = provider.elicitations
        let current = store.focused
        return [
          "waiting_count": "\(store.waitingCount)",
          "current_dispatch_id": current?.id ?? "",
          "current_mode": current?.mode.rawValue ?? "",
          "current_allows_free_text": current.map { $0.allowsFreeText ? "true" : "false" } ?? "",
          "composer_shows_card": current == nil ? "false" : "true",
        ]
      }

      register(
        name: "elicitation_focus",
        summary: "Move between queued questions without answering. DEBUG non-prod only.",
        params: ["direction", "dispatch_id"]
      ) { params in
        guard AppBuild.isNonProduction else {
          return ["error": "elicitation_focus is disabled on production bundles"]
        }
        guard let provider = ChatProvider.mainInstance else {
          return ["error": "main ChatProvider not yet initialized"]
        }
        let store = provider.elicitations
        if let dispatchID = params["dispatch_id"],
          let target = store.queue.first(where: { $0.id == dispatchID })
        {
          store.focus(target)
        } else if params["direction"] == "previous" {
          store.focusPrevious()
        } else {
          store.focusNext()
        }
        return [
          "current_dispatch_id": store.focused?.id ?? "",
          "focused_index": "\(store.focusedIndex)",
          "staged_here": store.stagedForFocused == nil ? "false" : "true",
        ]
      }

      register(
        name: "elicitation_stage",
        summary: "Choose an option without sending it. DEBUG non-prod only.",
        params: ["option_id", "text"]
      ) { params in
        guard AppBuild.isNonProduction else {
          return ["error": "elicitation_stage is disabled on production bundles"]
        }
        guard let provider = ChatProvider.mainInstance else {
          return ["error": "main ChatProvider not yet initialized"]
        }
        let store = provider.elicitations
        guard let current = store.focused else { return ["staged": "false"] }
        if let text = params["text"] {
          store.stage(.text(text), for: current)
        } else if let optionID = params["option_id"] {
          store.stage(.options([optionID]), for: current)
        }
        return [
          "staged": store.stagedForFocused == nil ? "false" : "true",
          "waiting_count": "\(store.waitingCount)",
        ]
      }

      register(
        name: "elicitation_cancel",
        summary: "Dismiss the current elicitation the way clicking Cancel would. DEBUG non-prod only."
      ) { _ in
        guard AppBuild.isNonProduction else {
          return ["error": "elicitation_cancel is disabled on production bundles"]
        }
        guard let provider = ChatProvider.mainInstance else {
          return ["error": "main ChatProvider not yet initialized"]
        }
        let store = provider.elicitations
        guard let current = store.focused else {
          return ["cancelled": "false", "waiting_count": "0"]
        }
        store.answer(current, with: .cancel)
        return [
          "cancelled": "true",
          "waiting_count": "\(store.waitingCount)",
          "current_dispatch_id": store.focused?.id ?? "",
        ]
      }

      register(
        name: "elicitation_answer",
        summary: "Answer the current elicitation the way clicking its option would. DEBUG non-prod only.",
        params: ["option_id"]
      ) { params in
        guard AppBuild.isNonProduction else {
          return ["error": "elicitation_answer is disabled on production bundles"]
        }
        guard let provider = ChatProvider.mainInstance else {
          return ["error": "main ChatProvider not yet initialized"]
        }
        let store = provider.elicitations
        guard let current = store.focused else {
          return ["answered": "false", "waiting_count": "0"]
        }
        // Never default to a remembered grant. The first option a permission
        // offers is often "Always Allow", and a QA helper that silently grants
        // one outlives the run it was testing.
        let fallback =
          current.options.first(where: { !$0.isPermanent && !$0.isRejection })
          ?? current.options.first(where: { !$0.isPermanent })
          ?? current.options.first
        let optionID = params["option_id"] ?? fallback?.id ?? ""
        store.stage(.options([optionID]), for: current)
        store.submitFocused()
        return [
          "answered": "true",
          "waiting_count": "\(store.waitingCount)",
          "current_dispatch_id": store.focused?.id ?? "",
        ]
      }
    #endif
  }
}
