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
          "current_dispatch_id": store.current?.id ?? "",
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
        let current = store.current
        return [
          "waiting_count": "\(store.waitingCount)",
          "current_dispatch_id": current?.id ?? "",
          "current_mode": current?.mode.rawValue ?? "",
          "current_allows_free_text": current.map { $0.allowsFreeText ? "true" : "false" } ?? "",
          "composer_shows_card": current == nil ? "false" : "true",
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
        guard let current = store.current else {
          return ["answered": "false", "waiting_count": "0"]
        }
        let optionID = params["option_id"] ?? current.options.first?.id ?? ""
        store.answer(current, with: .option(optionID))
        return [
          "answered": "true",
          "waiting_count": "\(store.waitingCount)",
          "current_dispatch_id": store.current?.id ?? "",
        ]
      }
    #endif
  }
}
