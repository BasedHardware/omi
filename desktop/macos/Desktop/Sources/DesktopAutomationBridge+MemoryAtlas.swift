import Foundation

/// Brain Map (memory atlas) actions: opening it, driving its camera and
/// selection, rebuilding it and reading its graph. Split from the base bridge
/// file for the product-file line-count ratchet; the flow lint and the
/// registry tests glob every `DesktopAutomationBridge*.swift`.
extension DesktopAutomationActionRegistry {
  func registerMemoryAtlasActions() {
    register(
      name: "memory_graph_rebuild",
      summary:
        "Press the Brain Map's Rebuild control: the server rebuild, or this Mac's own rebuild from every conversation, memory, person and goal when the server refuses. `wait_seconds` waits for the outcome.",
      params: ["wait_seconds"]
    ) { params in
      // Drives the same state the Rebuild button does, so an automated check
      // exercises the real path (server first, desktop fallback) rather than
      // a parallel API call that the button no longer makes. Mutating and not
      // undoable.
      //
      // The surface that takes the request acknowledges it synchronously while
      // the notification is delivered, so `accepted` is known on return: no
      // acknowledgement means no Brain Map surface is mounted. With
      // `wait_seconds` the call then waits for the rebuild to end and reports
      // how it went and which path it took.
      let waitSeconds = Double(params["wait_seconds"] ?? "") ?? 0
      let acknowledgement = NotificationWaiter(name: .desktopAutomationMemoryAtlasRebuildAcknowledged) { note in
        (accepted: note.userInfo?["accepted"] as? Bool ?? false, reason: note.userInfo?["reason"] as? String)
      }
      let finish = NotificationWaiter(name: .desktopAutomationMemoryAtlasRebuildFinished) { note in
        note.userInfo?["outcome"] as? MemoryAtlasRebuildOutcome
      }
      await MainActor.run {
        NotificationCenter.default.post(name: .desktopAutomationMemoryAtlasRebuildRequested, object: nil)
      }
      guard let acknowledged = await acknowledgement.wait(for: .seconds(2)) else {
        return ["posted": "true", "accepted": "false", "reason": "no_receiver"]
      }
      var detail: [String: String] = ["posted": "true", "accepted": acknowledged.accepted ? "true" : "false"]
      if let reason = acknowledged.reason { detail["reason"] = reason }
      guard acknowledged.accepted, waitSeconds > 0 else { return detail }
      guard let outcome = await finish.wait(for: .seconds(waitSeconds)) ?? nil else {
        detail["finished"] = "false"
        return detail
      }
      detail["finished"] = "true"
      detail["succeeded"] = outcome.succeeded ? "true" : "false"
      detail["path"] = outcome.path.rawValue
      detail["node_count"] = "\(outcome.nodeCount)"
      detail["edge_count"] = "\(outcome.edgeCount)"
      detail["detail"] = outcome.detail
      return detail
    }

    register(
      name: "memory_graph_snapshot",
      summary: "Return knowledge graph node/edge counts (no SceneKit rendering)",
      params: ["label"]
    ) { params in
      do {
        // What the map shows: the server graph with this Mac's rebuild under it.
        let graph = BrainMapLocalGraphMerge.merge(
          server: try await APIClient.shared.getKnowledgeGraph(),
          local: await BrainMapLocalRebuilder.storedGraph())
        let atlas = MemoryAtlasProjection(graph: graph.atlasResponse, userName: nil)
        var detail = [
          "node_count": "\(graph.nodes.count)",
          "edge_count": "\(graph.edges.count)",
          "catalog_memory_count": "\(graph.catalogNodes?.count ?? 0)",
          "atlas_mark_count": "\(atlas.snapshot.nodes.count)",
          "is_empty": graph.nodes.isEmpty ? "true" : "false",
        ]
        // A label resolves to the ids and citations the inspector needs.
        if let query = params["label"]?.lowercased(), !query.isEmpty {
          if let match = graph.nodes.first(where: { $0.label.lowercased().contains(query) }) {
            let edges = graph.edges.filter { $0.sourceId == match.id || $0.targetId == match.id }
            detail["match_id"] = match.id
            detail["match_label"] = match.label
            detail["match_edge_count"] = "\(edges.count)"
            detail["match_cited_memory_count"] = "\(Set(edges.flatMap(\.memoryIds)).count)"
            if let first = edges.first {
              detail["match_first_edge_id"] = first.id
              detail["match_first_edge_memory_count"] = "\(first.memoryIds.count)"
            }
          } else {
            detail["match_id"] = ""
          }
        }
        return detail
      } catch {
        return [
          "node_count": "0",
          "edge_count": "0",
          "is_empty": "true",
          "has_error": "true",
          "error_message": error.localizedDescription,
        ]
      }
    }

    register(
      name: "memory_atlas_select",
      summary: "Select a Brain Map entity or connection so the inspector can be checked cursor-free",
      params: ["target", "node_id", "label", "edge_id", "clear"]
    ) { params in
      let target = params["target"] == "inline" ? "inline" : "page"
      var userInfo: [String: Any] = ["target": target]
      if let nodeID = params["node_id"], !nodeID.isEmpty { userInfo["node_id"] = nodeID }
      if let label = params["label"], !label.isEmpty { userInfo["label"] = label }
      if let edgeID = params["edge_id"], !edgeID.isEmpty { userInfo["edge_id"] = edgeID }
      if params["clear"] == "true" { userInfo["clear"] = true }
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryAtlasSelectRequested,
          object: nil,
          userInfo: userInfo
        )
      }
      return [
        "posted": "true",
        "target": target,
        "node_id": params["node_id"] ?? "",
        "label": params["label"] ?? "",
        "edge_id": params["edge_id"] ?? "",
        "clear": params["clear"] ?? "false",
      ]
    }

    register(
      name: "open_memory_atlas",
      summary: "Open the canonical memory atlas page for non-production UI and performance harnesses"
    ) { _ in
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationOpenMemoryAtlasRequested,
          object: nil
        )
      }
      return ["opened": "true", "target": "page"]
    }

    register(
      name: "memory_atlas_set_viewport",
      summary: "Set memory atlas zoom and pan for deterministic non-production performance sweeps",
      params: ["target", "zoom", "pan_x", "pan_y", "reset"]
    ) { params in
      let target = params["target"] == "inline" ? "inline" : "page"
      var userInfo: [String: Any] = ["target": target]
      if let zoom = params["zoom"].flatMap(Double.init) { userInfo["zoom"] = zoom }
      if let panX = params["pan_x"].flatMap(Double.init) { userInfo["pan_x"] = panX }
      if let panY = params["pan_y"].flatMap(Double.init) { userInfo["pan_y"] = panY }
      if let reset = params["reset"] { userInfo["reset"] = reset == "true" }
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryAtlasViewportRequested,
          object: nil,
          userInfo: userInfo
        )
      }
      return [
        "posted": "true",
        "target": target,
        "zoom": params["zoom"] ?? "unchanged",
        "pan_x": params["pan_x"] ?? "unchanged",
        "pan_y": params["pan_y"] ?? "unchanged",
      ]
    }

    register(
      name: "memory_atlas_enter_region",
      summary: "Go into a Brain Map neighbourhood by caption, or leave the one you are in",
      params: ["target", "caption", "leave"]
    ) { params in
      let target = params["target"] == "inline" ? "inline" : "page"
      var userInfo: [String: Any] = ["target": target]
      if let caption = params["caption"] { userInfo["caption"] = caption }
      if let leave = params["leave"] { userInfo["leave"] = leave == "true" }
      await MainActor.run {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryAtlasRegionRequested,
          object: nil,
          userInfo: userInfo
        )
      }
      return [
        "posted": "true", "target": target,
        "caption": params["caption"] ?? "", "leave": params["leave"] ?? "false",
      ]
    }
  }
}
