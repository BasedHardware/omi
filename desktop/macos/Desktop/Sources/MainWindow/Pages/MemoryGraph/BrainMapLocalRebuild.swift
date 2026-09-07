import Foundation

// MARK: - Sources

/// One thing the account knows, as the text the extractor reads and the id the
/// map cites for it.
///
/// The desktop rebuild reads the same account the server rebuild does —
/// conversations, memories, people, goals — through the same citation ids, so a
/// map built here and a map built on the server are interchangeable to the
/// inspector. A memory keeps its own id; every other source is prefixed.
struct BrainMapRebuildSource: Equatable, Sendable {
  let id: String
  let text: String
}

enum BrainMapRebuildSources {
  static let conversationPrefix = MemoryAtlasEvidence.Citation.conversationPrefix
  static let peopleID = MemoryAtlasEvidence.Citation.peopleID
  static let goalsID = MemoryAtlasEvidence.Citation.goalsID
  /// A long meeting is cut to its summary plus the opening of its transcript
  /// rather than dropped; the summary is the server's and survives the cut.
  static let maxConversationChars = 4_000
  static let maxTranscriptChars = 2_400

  static func conversation(_ conversation: ServerConversation) -> BrainMapRebuildSource? {
    let text = conversationText(conversation)
    guard !text.isEmpty, !conversation.id.isEmpty else { return nil }
    return BrainMapRebuildSource(id: conversationPrefix + conversation.id, text: text)
  }

  /// Title, topic and summary lead because they are the server's own reading
  /// of the conversation; action items and events name the concrete things it
  /// was about; the transcript comes last and is the part that gets cut.
  static func conversationText(_ conversation: ServerConversation) -> String {
    var lines: [String] = []
    let title = conversation.structured.title.trimmingCharacters(in: .whitespacesAndNewlines)
    if !title.isEmpty { lines.append("Conversation: \(title)") }
    let category = conversation.structured.category.trimmingCharacters(in: .whitespacesAndNewlines)
    if !category.isEmpty, category != "other" { lines.append("Topic: \(category)") }
    let overview = conversation.structured.overview.trimmingCharacters(in: .whitespacesAndNewlines)
    if !overview.isEmpty { lines.append("Summary: \(overview)") }
    let actionItems = conversation.structured.actionItems.map(\.description).filter { !$0.isEmpty }
    if !actionItems.isEmpty { lines.append("Action items: " + actionItems.joined(separator: "; ")) }
    let events = conversation.structured.events.map(\.title).filter { !$0.isEmpty }
    if !events.isEmpty { lines.append("Events: " + events.joined(separator: "; ")) }
    var transcript = conversation.transcriptSegments.map(\.text).filter { !$0.isEmpty }.joined(separator: " ")
    if !transcript.isEmpty {
      if transcript.count > maxTranscriptChars {
        transcript = String(transcript.prefix(maxTranscriptChars)).trimmingCharacters(in: .whitespaces) + "…"
      }
      lines.append("Transcript: \(transcript)")
    }
    var text = lines.joined(separator: "\n")
    if text.count > maxConversationChars {
      text = String(text.prefix(maxConversationChars)).trimmingCharacters(in: .whitespaces) + "…"
    }
    return text
  }

  static func memory(id: String, content: String) -> BrainMapRebuildSource? {
    let text = content.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty, !id.isEmpty else { return nil }
    return BrainMapRebuildSource(id: id, text: text)
  }

  /// The whole people directory as one source, so a rebuild spends one
  /// extraction on it rather than one per person.
  static func people(names: [String]) -> BrainMapRebuildSource? {
    let cleaned = Set(names.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty })
    guard !cleaned.isEmpty else { return nil }
    return BrainMapRebuildSource(
      id: peopleID,
      text: "People the user knows and talks with: " + cleaned.sorted().joined(separator: ", ") + ".")
  }

  static func goals(_ goals: [(title: String, description: String?)]) -> BrainMapRebuildSource? {
    let lines = goals.compactMap { goal -> String? in
      let title = goal.title.trimmingCharacters(in: .whitespacesAndNewlines)
      let description = goal.description?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      if title.isEmpty && description.isEmpty { return nil }
      if description.isEmpty || description == title { return title }
      return title.isEmpty ? description : "\(title) — \(description)"
    }
    guard !lines.isEmpty else { return nil }
    return BrainMapRebuildSource(
      id: goalsID, text: "Goals the user is working toward: " + lines.joined(separator: "; ") + ".")
  }
}

// MARK: - Batching

/// The extract endpoint allows thirty calls an hour per account, so a rebuild
/// cannot spend one call per conversation. Sources are packed into a bounded
/// number of batches by character budget, in the order given (most recent
/// first), and whatever does not fit is left for the next rebuild.
enum BrainMapExtractionBatches {
  /// Under the hourly limit with room for a retry or a second rebuild.
  static let maxBatches = 24
  /// One extraction reads the whole batch in a single prompt; this keeps the
  /// prompt well inside the endpoint's own 100k-character ceiling.
  static let charBudget = 24_000

  static func make(
    _ sources: [BrainMapRebuildSource],
    charBudget: Int = charBudget,
    maxBatches: Int = maxBatches
  ) -> [[BrainMapRebuildSource]] {
    var batches: [[BrainMapRebuildSource]] = []
    var current: [BrainMapRebuildSource] = []
    var currentChars = 0
    for source in sources {
      let chars = source.text.count + 2
      if !current.isEmpty, currentChars + chars > charBudget {
        batches.append(current)
        current = []
        currentChars = 0
        if batches.count == maxBatches { return batches }
      }
      current.append(source)
      currentChars += chars
    }
    if !current.isEmpty, batches.count < maxBatches { batches.append(current) }
    return batches
  }

  /// One prompt per batch: each source is its own paragraph so the extractor
  /// reads them as separate events rather than one run-on story.
  static func text(for batch: [BrainMapRebuildSource]) -> String {
    batch.map(\.text).joined(separator: "\n\n")
  }
}

// MARK: - Citations

/// Which sources in a batch an extracted entity came from.
///
/// The endpoint returns entities for the whole batch, not per source, so the
/// map cites the sources whose text names the entity. An entity no source
/// names outright (the extractor inferred it) cites the whole batch: that is
/// less precise than wrong.
enum BrainMapCitationAttribution {
  static func citations(for node: KnowledgeGraphNode, in batch: [BrainMapRebuildSource]) -> [String] {
    let terms = ([node.label] + node.aliases)
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
      .filter { $0.count >= 2 }
    guard !terms.isEmpty else { return batch.map(\.id) }
    let named = batch.filter { source in
      let haystack = source.text.lowercased()
      return terms.contains { haystack.contains($0) }
    }
    return (named.isEmpty ? batch : named).map(\.id)
  }
}

// MARK: - Assembly

/// Folds the extractions of every batch into one local graph.
///
/// Entities are keyed by label, so "Omi" from one batch and "omi" from another
/// are the same node, and every node id carries the rebuild prefix so a later
/// rebuild can replace exactly these rows and nothing else in the local store.
enum BrainMapLocalGraphAssembly {
  static let nodeIDPrefix = "brainmap:"

  struct Assembled: Equatable {
    var nodes: [KnowledgeGraphNode]
    var edges: [KnowledgeGraphEdge]
  }

  /// The label as entities are keyed: case and surrounding whitespace do not
  /// distinguish two mentions, everything else does.
  static func normalizedLabel(_ label: String) -> String {
    label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      .split(whereSeparator: \.isWhitespace).joined(separator: " ")
  }

  /// A readable slug for the logs, made unique by a hash of the normalized
  /// label: "A-B", "A B" and "a.b" slug alike but are not the same entity.
  static func nodeID(for label: String) -> String {
    let normalized = normalizedLabel(label)
    let slug =
      normalized
      .components(separatedBy: CharacterSet.alphanumerics.inverted)
      .filter { !$0.isEmpty }
      .joined(separator: "-")
    return nodeIDPrefix + (slug.isEmpty ? "entity" : String(slug.prefix(40))) + "-" + stableHash(normalized)
  }

  /// FNV-1a over the UTF-8 bytes, as eight hex digits. `hashValue` is seeded
  /// per process and would give the same entity a new id on every launch.
  static func stableHash(_ text: String) -> String {
    var hash: UInt64 = 0xcbf2_9ce4_8422_2325
    for byte in text.utf8 {
      hash ^= UInt64(byte)
      hash = hash &* 0x0000_0100_0000_01b3
    }
    return String(format: "%08x", UInt32(truncatingIfNeeded: hash ^ (hash >> 32)))
  }

  static func assemble(
    _ extractions: [(batch: [BrainMapRebuildSource], graph: KnowledgeGraphExtractResponse)],
    now: Date = Date()
  ) -> Assembled {
    var nodesByID: [String: KnowledgeGraphNode] = [:]
    var order: [String] = []
    var edgesByKey: [String: KnowledgeGraphEdge] = [:]
    var edgeOrder: [String] = []

    for (batch, graph) in extractions {
      var idMap: [String: String] = [:]
      for node in graph.nodes {
        let label = node.label.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !label.isEmpty else { continue }
        let localID = nodeID(for: label)
        idMap[node.id] = localID
        let citations = BrainMapCitationAttribution.citations(for: node, in: batch)
        if let existing = nodesByID[localID] {
          nodesByID[localID] = KnowledgeGraphNode(
            id: localID,
            label: existing.label,
            nodeType: existing.nodeType,
            aliases: Array(Set(existing.aliases + node.aliases)).sorted(),
            memoryIds: Array(Set(existing.memoryIds + citations)).sorted(),
            createdAt: existing.createdAt,
            updatedAt: now)
        } else {
          order.append(localID)
          nodesByID[localID] = KnowledgeGraphNode(
            id: localID,
            label: label,
            nodeType: node.nodeType,
            aliases: Array(Set(node.aliases)).sorted(),
            memoryIds: citations.sorted(),
            createdAt: now,
            updatedAt: now)
        }
      }
      for edge in graph.edges {
        guard let source = idMap[edge.sourceId], let target = idMap[edge.targetId], source != target else { continue }
        let label = edge.label.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !label.isEmpty else { continue }
        let key = "\(source)|\(target)|\(label.lowercased())"
        let citations = Set(nodesByID[source]?.memoryIds ?? []).intersection(nodesByID[target]?.memoryIds ?? [])
        if let existing = edgesByKey[key] {
          edgesByKey[key] = KnowledgeGraphEdge(
            id: existing.id, sourceId: source, targetId: target, label: existing.label,
            memoryIds: Array(Set(existing.memoryIds).union(citations)).sorted(), createdAt: existing.createdAt)
        } else {
          edgeOrder.append(key)
          let slug = label.lowercased().replacingOccurrences(of: " ", with: "_")
          edgesByKey[key] = KnowledgeGraphEdge(
            id: "\(nodeIDPrefix)edge:\(source)|\(target)|\(slug)", sourceId: source, targetId: target,
            label: label, memoryIds: citations.sorted(), createdAt: now)
        }
      }
    }
    return Assembled(
      nodes: order.compactMap { nodesByID[$0] },
      edges: edgeOrder.compactMap { edgesByKey[$0] })
  }
}

// MARK: - Merge with the server graph

/// The server's graph with the local rebuild folded under it, server winning.
///
/// A local entity whose label or alias names a server entity lands on the
/// server id and only adds its citations, so the account holder extracted
/// from a conversation is the same node the assertions already know.
enum BrainMapLocalGraphMerge {
  static func merge(server: KnowledgeGraphResponse, local: KnowledgeGraphResponse) -> KnowledgeGraphResponse {
    guard !local.nodes.isEmpty else { return server }
    var nodesByID: [String: KnowledgeGraphNode] = [:]
    var order: [String] = []
    var idByTerm: [String: String] = [:]
    func terms(_ node: KnowledgeGraphNode) -> [String] {
      ([node.label] + node.aliases).map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        .filter { !$0.isEmpty }
    }
    for node in server.nodes {
      nodesByID[node.id] = node
      order.append(node.id)
      for term in terms(node) where idByTerm[term] == nil { idByTerm[term] = node.id }
    }

    var localIDMap: [String: String] = [:]
    for node in local.nodes {
      let match = terms(node).lazy.compactMap { idByTerm[$0] }.first
      let resolvedID = match ?? node.id
      localIDMap[node.id] = resolvedID
      if let existing = nodesByID[resolvedID] {
        nodesByID[resolvedID] = KnowledgeGraphNode(
          id: existing.id,
          label: existing.label,
          nodeType: existing.nodeType,
          aliases: Array(Set(existing.aliases + node.aliases)).sorted(),
          memoryIds: Array(Set(existing.memoryIds + node.memoryIds)).sorted(),
          createdAt: min(existing.createdAt, node.createdAt),
          updatedAt: max(existing.updatedAt, node.updatedAt))
      } else {
        nodesByID[resolvedID] = node
        order.append(resolvedID)
      }
      for term in terms(node) where idByTerm[term] == nil { idByTerm[term] = resolvedID }
    }

    var edgesByKey: [String: KnowledgeGraphEdge] = [:]
    var edgeOrder: [String] = []
    func key(_ edge: KnowledgeGraphEdge) -> String { "\(edge.sourceId)|\(edge.targetId)|\(edge.label.lowercased())" }
    for edge in server.edges {
      let edgeKey = key(edge)
      if edgesByKey[edgeKey] == nil { edgeOrder.append(edgeKey) }
      edgesByKey[edgeKey] = edge
    }
    for edge in local.edges {
      guard let source = localIDMap[edge.sourceId], let target = localIDMap[edge.targetId], source != target,
        nodesByID[source] != nil, nodesByID[target] != nil
      else { continue }
      let remapped = KnowledgeGraphEdge(
        id: edge.id, sourceId: source, targetId: target, label: edge.label,
        memoryIds: edge.memoryIds, createdAt: edge.createdAt)
      let edgeKey = key(remapped)
      if let existing = edgesByKey[edgeKey] {
        edgesByKey[edgeKey] = KnowledgeGraphEdge(
          id: existing.id, sourceId: existing.sourceId, targetId: existing.targetId, label: existing.label,
          memoryIds: Array(Set(existing.memoryIds + remapped.memoryIds)).sorted(), createdAt: existing.createdAt)
      } else {
        edgeOrder.append(edgeKey)
        edgesByKey[edgeKey] = remapped
      }
    }

    return KnowledgeGraphResponse(
      nodes: order.compactMap { nodesByID[$0] },
      edges: edgeOrder.compactMap { edgesByKey[$0] },
      hasMore: server.hasMore,
      nextCursor: server.nextCursor,
      eligibleItemCount: server.eligibleItemCount,
      processedItemCount: server.processedItemCount,
      catalogNodes: server.catalogNodes,
      rebuild: server.rebuild)
  }
}

// MARK: - The rebuild itself

/// Rebuilds the Brain Map on this Mac from everything the account knows.
///
/// This is the path a server that refuses to rebuild leaves open: the same
/// sources the server rebuild reads, extracted through the server's own
/// return-only extract endpoint, persisted in the local knowledge graph store
/// and merged under the server graph on every read. Progress is reported as
/// short sentences for the Rebuild button.
///
/// The map the user has is replaced only by a whole one. Every source is read
/// or the rebuild fails; every batch is extracted (with one retry) or the
/// rebuild fails; nothing is written to the store until both hold, so a
/// rebuild that runs short leaves the previous map exactly as it was.
enum BrainMapLocalRebuilder {
  struct Report: Equatable {
    var conversations = 0
    var memories = 0
    var people = 0
    var goals = 0
    var batches = 0
    /// Batches that failed once and were extracted on the retry.
    var retriedBatches = 0
    var nodes = 0
    var edges = 0
  }

  enum Failure: Error, Equatable {
    case nothingToRead
    /// One of the account's sources could not be read; the map is unchanged.
    case sourceUnreadable(String)
    /// `failed` of `total` batches still failed after their retry; the map is unchanged.
    case extractionIncomplete(failed: Int, of: Int)

    var localizedDescription: String {
      switch self {
      case .nothingToRead: return "nothing to read"
      case .sourceUnreadable(let source): return "could not read \(source)"
      case .extractionIncomplete(let failed, let total): return "\(failed) of \(total) batches failed"
      }
    }
  }

  static let conversationPageSize = 100
  /// Most recent first; the batch budget decides how many are actually read.
  static let maxConversations = 400
  static let maxMemories = 500
  /// How long a failed batch waits before its one retry.
  static let retryDelay: Duration = .seconds(2)

  typealias Extract = @Sendable (String) async throws -> KnowledgeGraphExtractResponse

  /// Everything the rebuild reads, as seams so a test can drive the run
  /// without a server; the defaults are the API, pinned to the authorization
  /// the rebuild started under.
  struct Reads: Sendable {
    var conversations: @Sendable (_ limit: Int, _ offset: Int) async throws -> [ServerConversation]
    var memories: @Sendable (_ limit: Int) async throws -> [ServerMemory]
    var people: @Sendable () async throws -> [Person]
    var goals: @Sendable () async throws -> [Goal]

    static func live(authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot) -> Reads {
      Reads(
        conversations: { limit, offset in
          try await APIClient.shared.getConversations(
            limit: limit, offset: offset, authorizationSnapshot: authorizationSnapshot)
        },
        memories: { limit in
          try await APIClient.shared.getMemories(limit: limit, authorizationSnapshot: authorizationSnapshot)
        },
        people: { try await APIClient.shared.getPeople() },
        goals: { try await APIClient.shared.getGoals(authorizationSnapshot: authorizationSnapshot) })
    }
  }

  /// Where the finished graph goes; the local knowledge-graph store by default.
  typealias Store =
    @Sendable ([LocalKGNodeRecord], [LocalKGEdgeRecord], LocalMutationAuthorization) async throws ->
    Void

  /// Where a rebuild is, as a fraction the bar can fill to. Reading the
  /// account is the first tenth, extraction the middle four fifths (one
  /// batch at a time), saving and reloading the rest.
  struct Progress: Equatable, Sendable {
    let label: String
    let fraction: Double

    static func extracting(completed: Int, of total: Int) -> Progress {
      Progress(
        label: "Extracting \(completed) of \(total)…",
        fraction: 0.1 + 0.8 * Double(completed) / Double(max(total, 1)))
    }
  }

  static func run(
    reads: Reads,
    isAuthorizationCurrent: @escaping @Sendable () -> Bool,
    progress: @MainActor @escaping (Progress) -> Void,
    extract: Extract = { text in
      try await APIClient.shared.extractKnowledgeGraph(text: text, includeExisting: false)
    },
    store: Store = { nodes, edges, authorization in
      try await KnowledgeGraphStorage.shared.replaceRebuiltGraph(
        nodes: nodes, edges: edges, authorization: authorization)
    },
    retryDelay: Duration = retryDelay
  ) async throws -> Report {
    var report = Report()
    var sources: [BrainMapRebuildSource] = []

    await progress(Progress(label: "Reading conversations…", fraction: 0.02))
    var offset = 0
    var conversations: [ServerConversation] = []
    while conversations.count < maxConversations {
      let page: [ServerConversation]
      do {
        page = try await reads.conversations(conversationPageSize, offset)
      } catch {
        throw readFailure("conversations", error)
      }
      conversations.append(contentsOf: page)
      if page.count < conversationPageSize { break }
      offset += page.count
    }
    for conversation in conversations {
      if let source = BrainMapRebuildSources.conversation(conversation) {
        sources.append(source)
        report.conversations += 1
      }
    }

    await progress(Progress(label: "Reading memories…", fraction: 0.07))
    let memories: [ServerMemory]
    do {
      memories = try await reads.memories(maxMemories)
    } catch {
      throw readFailure("memories", error)
    }
    for memory in memories {
      if let source = BrainMapRebuildSources.memory(id: memory.id, content: memory.content) {
        sources.append(source)
        report.memories += 1
      }
    }
    let people: [Person]
    do {
      people = try await reads.people()
    } catch {
      throw readFailure("people", error)
    }
    if let source = BrainMapRebuildSources.people(names: people.map(\.name)) {
      sources.append(source)
      report.people = people.count
    }
    let goals: [Goal]
    do {
      goals = try await reads.goals()
    } catch {
      throw readFailure("goals", error)
    }
    if let source = BrainMapRebuildSources.goals(goals.map { (title: $0.title, description: $0.description) }) {
      sources.append(source)
      report.goals = goals.count
    }
    guard !sources.isEmpty else { throw Failure.nothingToRead }

    let batches = BrainMapExtractionBatches.make(sources)
    report.batches = batches.count
    var extractions: [(batch: [BrainMapRebuildSource], graph: KnowledgeGraphExtractResponse)] = []
    var failedBatches = 0
    for (index, batch) in batches.enumerated() {
      guard isAuthorizationCurrent() else { throw LocalMutationAuthorizationError.revoked }
      await progress(.extracting(completed: index, of: batches.count))
      let text = BrainMapExtractionBatches.text(for: batch)
      do {
        extractions.append((batch, try await extract(text)))
      } catch {
        // One retry after a pause covers the transient answer; a second
        // failure is the account's rate limit or a server that is down, and
        // neither is worth a partial map.
        log("Brain Map local rebuild: batch \(index + 1) failed, retrying: \(error.localizedDescription)")
        try? await Task.sleep(for: retryDelay)
        guard isAuthorizationCurrent() else { throw LocalMutationAuthorizationError.revoked }
        do {
          extractions.append((batch, try await extract(text)))
          report.retriedBatches += 1
        } catch {
          failedBatches += 1
          log("Brain Map local rebuild: batch \(index + 1) failed again: \(error.localizedDescription)")
        }
      }
    }
    guard failedBatches == 0 else {
      throw Failure.extractionIncomplete(failed: failedBatches, of: batches.count)
    }

    await progress(Progress(label: "Saving…", fraction: 0.92))
    let assembled = BrainMapLocalGraphAssembly.assemble(extractions)
    report.nodes = assembled.nodes.count
    report.edges = assembled.edges.count
    let now = Date()
    let nodeRecords = assembled.nodes.map { node in
      LocalKGNodeRecord(
        nodeId: node.id,
        label: node.label,
        nodeType: node.nodeType.rawValue,
        aliasesJson: String(data: (try? JSONEncoder().encode(node.aliases)) ?? Data(), encoding: .utf8),
        sourceFileIds: String(data: (try? JSONEncoder().encode(node.memoryIds)) ?? Data(), encoding: .utf8),
        createdAt: now,
        updatedAt: now)
    }
    let edgeRecords = assembled.edges.map { edge in
      LocalKGEdgeRecord(
        edgeId: edge.id, sourceNodeId: edge.sourceId, targetNodeId: edge.targetId, label: edge.label,
        createdAt: now,
        memoryIdsJson: String(data: (try? JSONEncoder().encode(edge.memoryIds)) ?? Data(), encoding: .utf8))
    }
    try await store(nodeRecords, edgeRecords, LocalMutationAuthorization(isAuthorizationCurrent))
    return report
  }

  private static func readFailure(_ source: String, _ error: Error) -> Error {
    log("Brain Map local rebuild: could not read \(source): \(error.localizedDescription)")
    return Failure.sourceUnreadable(source)
  }

  /// The locally rebuilt part of the local store: only rows this rebuild
  /// wrote, never the file-index or chat-tool entities that share the tables.
  static func storedGraph() async -> KnowledgeGraphResponse {
    let stored = await KnowledgeGraphStorage.shared.loadGraph()
    let nodes = stored.nodes.filter { $0.id.hasPrefix(BrainMapLocalGraphAssembly.nodeIDPrefix) }
    guard !nodes.isEmpty else { return KnowledgeGraphResponse(nodes: [], edges: []) }
    let nodeIDs = Set(nodes.map(\.id))
    let edges = stored.edges.filter { nodeIDs.contains($0.sourceId) && nodeIDs.contains($0.targetId) }
    return KnowledgeGraphResponse(nodes: nodes, edges: edges)
  }
}
