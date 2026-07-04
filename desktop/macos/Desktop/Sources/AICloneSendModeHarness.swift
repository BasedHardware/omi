import Foundation

/// Headless automation actions for the AI Clone send-mode system, registered on the local
/// automation bridge (non-production bundles only). They let an agent drive and inspect the
/// send pipeline — per-contact mode, the autonomous kill switch, the pending-draft queue,
/// the sent log, and both the Draft-Review generation path and the real routed send — without
/// clicking through the UI.
///
/// Actions:
///   ai_clone_sendmode_status                     — paused flag, mode/pending/sent counts
///   ai_clone_set_paused paused=true|false        — flip the global kill switch
///   ai_clone_set_mode contact_id=… mode=…        — set a contact's send mode
///   ai_clone_simulate_incoming contact_id=… text=… — feed a fake incoming (needs a persona)
///   ai_clone_pending                             — dump the pending-draft queue
///   ai_clone_sent                                — dump the recent-sent log
///   ai_clone_send_routed contact_id=… text=…     — send through the real routed send + log
enum AICloneSendModeHarness {

  @MainActor
  static func register(on registry: DesktopAutomationActionRegistry) {
    let service = AICloneSendModeService.shared

    registry.register(
      name: "ai_clone_sendmode_status",
      summary: "Report the AI Clone send-mode state (paused flag + counts)"
    ) { _ in
      [
        "isPaused": service.isPaused ? "true" : "false",
        "pendingDrafts": String(service.pendingDrafts.count),
        "sentLog": String(service.sentLog.count),
      ]
    }

    registry.register(
      name: "ai_clone_set_paused",
      summary: "Set the global autonomous kill switch (true = paused/safe)",
      params: ["paused"]
    ) { params in
      guard let raw = params["paused"] else { return ["error": "missing 'paused'"] }
      let paused = (raw as NSString).boolValue
      service.setPaused(paused)
      return ["isPaused": service.isPaused ? "true" : "false"]
    }

    registry.register(
      name: "ai_clone_set_mode",
      summary: "Set a contact's send mode (manual | draftReview | autonomous)",
      params: ["contact_id", "mode"]
    ) { params in
      guard let contactId = params["contact_id"], !contactId.isEmpty else {
        return ["error": "missing 'contact_id'"]
      }
      guard let raw = params["mode"], let mode = SendMode(rawValue: raw) else {
        return ["error": "invalid 'mode' (manual | draftReview | autonomous)"]
      }
      let accepted = service.setMode(mode, for: contactId)
      if !accepted {
        return [
          "error":
            "blocked: WhatsApp Autonomous requires the one-time unofficial-connection risk acknowledgment",
          "contact_id": contactId,
          "mode": service.mode(for: contactId).rawValue,
        ]
      }
      return ["contact_id": contactId, "mode": service.mode(for: contactId).rawValue]
    }

    registry.register(
      name: "ai_clone_simulate_incoming",
      summary:
        "Simulate an incoming message from a trained contact (drives Draft-Review/Autonomous)",
      params: ["contact_id", "text"]
    ) { params in
      guard let contactId = params["contact_id"], !contactId.isEmpty else {
        return ["error": "missing 'contact_id'"]
      }
      guard let text = params["text"], !text.isEmpty else { return ["error": "missing 'text'"] }
      guard let persona = await AIClonePersonaService.shared.allPersonas()[contactId] else {
        return ["error": "no trained persona for \(contactId) — train it first"]
      }
      // Register the contact so the coordinator's router recognizes it, then feed the event.
      let contact = ImportedContact(
        id: contactId,
        displayName: persona.contactHandle,
        messageCount: persona.messageCountUsed,
        platform: AIClonePlatform.of(contactId: contactId).rawValue)
      service.updateActiveContacts([(contact, persona)])

      let platform = AIClonePlatform.of(contactId: contactId)
      let peerKey: String
      switch platform {
      case .imessage: peerKey = contactId
      case .telegram: peerKey = String(contactId.dropFirst("telegram:".count))
      case .whatsapp: peerKey = String(contactId.dropFirst("whatsapp:".count))
      }
      service.handleIncoming(
        platform: platform, peerKey: peerKey, fromMe: false, text: text, date: Date())
      return [
        "accepted": "true",
        "mode": service.mode(for: contactId).rawValue,
        "isPaused": service.isPaused ? "true" : "false",
        "note": "check ai_clone_pending / ai_clone_sent after a moment (generation is async)",
      ]
    }

    registry.register(
      name: "ai_clone_pending",
      summary: "Dump the pending Draft-Review queue"
    ) { _ in
      let lines = service.pendingDrafts.enumerated().map { i, d in
        "\(i). [\(d.contactDisplayName)] incoming=\"\(d.incomingText)\" draft=\"\(d.draftText)\""
      }
      return ["count": String(service.pendingDrafts.count), "drafts": lines.joined(separator: "\n")]
    }

    registry.register(
      name: "ai_clone_sent",
      summary: "Dump the recent-sent log"
    ) { _ in
      let lines = service.recentSent(limit: 20).map { e in
        "[\(e.mode.rawValue)] \(e.contactDisplayName): \"\(e.text)\""
      }
      return ["count": String(service.sentLog.count), "sent": lines.joined(separator: "\n")]
    }

    registry.register(
      name: "ai_clone_send_routed",
      summary: "Send text through the real routed send (platform dispatch + log); newlines split into separate burst messages",
      params: ["contact_id", "text"]
    ) { params in
      guard let contactId = params["contact_id"], !contactId.isEmpty else {
        return ["error": "missing 'contact_id'"]
      }
      guard let text = params["text"], !text.isEmpty else { return ["error": "missing 'text'"] }
      let name =
        await AIClonePersonaService.shared.allPersonas()[contactId]?.contactHandle ?? contactId
      do {
        try await service.sendBubbles(
          contactId: contactId, displayName: name, text: text, mode: .manual)
        return [
          "sent": "true", "contact_id": contactId,
          "bubbles": String(AICloneReplyPresentation.bubbles(from: text).count),
        ]
      } catch {
        return ["error": error.localizedDescription]
      }
    }
  }
}
