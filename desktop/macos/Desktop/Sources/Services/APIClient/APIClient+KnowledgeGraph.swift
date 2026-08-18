import Foundation
import OmiWAL

// MARK: - Knowledge Graph Models

/// Node type in the knowledge graph
enum KnowledgeGraphNodeType: String, Codable, Sendable {
  case person
  case place
  case organization
  case thing
  case concept
}

/// A node in the knowledge graph representing an entity
struct KnowledgeGraphNode: Codable, Equatable, Identifiable, Sendable {
  let id: String
  let label: String
  let nodeType: KnowledgeGraphNodeType
  let aliases: [String]
  let memoryIds: [String]
  let createdAt: Date
  let updatedAt: Date

  enum CodingKeys: String, CodingKey {
    case id, label, aliases
    case nodeType = "node_type"
    case memoryIds = "memory_ids"
    case createdAt = "created_at"
    case updatedAt = "updated_at"
  }

  init(
    id: String, label: String, nodeType: KnowledgeGraphNodeType, aliases: [String] = [],
    memoryIds: [String] = [], createdAt: Date = Date(), updatedAt: Date = Date()
  ) {
    self.id = id
    self.label = label
    self.nodeType = nodeType
    self.aliases = aliases
    self.memoryIds = memoryIds
    self.createdAt = createdAt
    self.updatedAt = updatedAt
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    label = try container.decode(String.self, forKey: .label)
    if let rawType = try container.decodeIfPresent(String.self, forKey: .nodeType) {
      nodeType = KnowledgeGraphNodeType(rawValue: rawType) ?? .concept
    } else {
      nodeType = .concept
    }
    aliases = try container.decodeIfPresent([String].self, forKey: .aliases) ?? []
    memoryIds = try container.decodeIfPresent([String].self, forKey: .memoryIds) ?? []
    // Missing legacy timestamps must not make a duplicate merge depend on
    // which page happened to decode first.
    let missingTimestamp = Date(timeIntervalSince1970: 0)
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? missingTimestamp
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? missingTimestamp
  }
}

/// An edge in the knowledge graph representing a relationship
struct KnowledgeGraphEdge: Codable, Equatable, Identifiable, Sendable {
  let id: String
  let sourceId: String
  let targetId: String
  let label: String
  let memoryIds: [String]
  let createdAt: Date

  enum CodingKeys: String, CodingKey {
    case id, label
    case sourceId = "source_id"
    case targetId = "target_id"
    case memoryIds = "memory_ids"
    case createdAt = "created_at"
  }

  init(
    id: String, sourceId: String, targetId: String, label: String, memoryIds: [String] = [],
    createdAt: Date = Date()
  ) {
    self.id = id
    self.sourceId = sourceId
    self.targetId = targetId
    self.label = label
    self.memoryIds = memoryIds
    self.createdAt = createdAt
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    sourceId = try container.decode(String.self, forKey: .sourceId)
    targetId = try container.decode(String.self, forKey: .targetId)
    label = try container.decode(String.self, forKey: .label)
    memoryIds = try container.decodeIfPresent([String].self, forKey: .memoryIds) ?? []
    // Keep decoding deterministic when an older response omits timestamps.
    createdAt =
      try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date(timeIntervalSince1970: 0)
  }
}

/// A page or complete response containing the knowledge graph.
///
/// Legacy `/v1/knowledge-graph` responses omit the pagination fields and are
/// decoded as a single, complete page. The alias below gives page-oriented
/// callers an explicit contract without duplicating the node/edge wire models.
struct KnowledgeGraphResponse: Codable, Equatable, Sendable {
  static let defaultPageSize = 200
  static let maximumPageSize = 500

  let nodes: [KnowledgeGraphNode]
  let edges: [KnowledgeGraphEdge]
  let hasMore: Bool
  let nextCursor: String?
  let eligibleItemCount: Int?
  let processedItemCount: Int?
  /// Optional additive catalog records. These are durable memory nodes, not
  /// assertion-backed graph nodes, and are intentionally excluded from atlas
  /// layout and counts.
  let catalogNodes: [KnowledgeGraphNode]?

  enum CodingKeys: String, CodingKey {
    case nodes, edges
    case hasMore = "has_more"
    case nextCursor = "next_cursor"
    case eligibleItemCount = "eligible_item_count"
    case processedItemCount = "processed_item_count"
    case catalogNodes = "catalog_nodes"
  }

  init(
    nodes: [KnowledgeGraphNode],
    edges: [KnowledgeGraphEdge],
    hasMore: Bool = false,
    nextCursor: String? = nil,
    eligibleItemCount: Int? = nil,
    processedItemCount: Int? = nil,
    catalogNodes: [KnowledgeGraphNode]? = nil
  ) {
    self.nodes = nodes
    self.edges = edges
    self.hasMore = hasMore
    self.nextCursor = nextCursor
    self.eligibleItemCount = eligibleItemCount
    self.processedItemCount = processedItemCount
    self.catalogNodes = catalogNodes
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    nodes = try container.decode([KnowledgeGraphNode].self, forKey: .nodes)
    edges = try container.decode([KnowledgeGraphEdge].self, forKey: .edges)
    hasMore = try container.decodeIfPresent(Bool.self, forKey: .hasMore) ?? false
    nextCursor = try container.decodeIfPresent(String.self, forKey: .nextCursor)
    eligibleItemCount = try container.decodeIfPresent(Int.self, forKey: .eligibleItemCount)
    processedItemCount = try container.decodeIfPresent(Int.self, forKey: .processedItemCount)
    catalogNodes = try container.decodeIfPresent([KnowledgeGraphNode].self, forKey: .catalogNodes)
  }

  /// Nodes that are safe for the atlas to lay out. The canonical endpoint's
  /// `nodes` field is assertion-backed; older canonical payloads that predate
  /// `catalog_nodes` may still have isolated catalog nodes folded into it, so
  /// those are excluded by their stable `memory:` id prefix.
  var atlasNodes: [KnowledgeGraphNode] {
    if catalogNodes != nil { return nodes }
    return nodes.filter { !$0.id.hasPrefix("memory:") }
  }

  /// A graph-shaped view for projection caches. It retains the catalog on the
  /// response model while ensuring node consumers receive assertion-backed
  /// nodes only.
  var atlasResponse: KnowledgeGraphResponse {
    KnowledgeGraphResponse(
      nodes: atlasNodes,
      edges: edges,
      hasMore: hasMore,
      nextCursor: nextCursor,
      eligibleItemCount: eligibleItemCount,
      processedItemCount: processedItemCount,
      catalogNodes: catalogNodes)
  }

  /// Deterministically unions pages and removes edges whose endpoints were not
  /// present in the final node union. Sorting and field-level set unions make
  /// this independent of page order or duplicate placement.
  static func merged(pages: [KnowledgeGraphResponse]) -> KnowledgeGraphResponse {
    var accumulator = KnowledgeGraphAccumulator()
    for page in pages { accumulator.append(page) }
    return accumulator.response()
  }
}

typealias KnowledgeGraphPageResponse = KnowledgeGraphResponse

/// Order-independent graph union used only for the in-memory canonical fetch.
/// It deliberately has no storage side effects: canonical pages are never
/// written to `KnowledgeGraphStorage`.
struct KnowledgeGraphAccumulator: Sendable {
  private var nodesByID: [String: KnowledgeGraphNode] = [:]
  private var edgesByID: [String: KnowledgeGraphEdge] = [:]
  private var catalogNodesByID: [String: KnowledgeGraphNode]?
  private var eligibleItemCount: Int?
  private var processedItemCount: Int?

  mutating func append(_ page: KnowledgeGraphResponse) {
    for node in page.nodes {
      if let existing = nodesByID[node.id] {
        nodesByID[node.id] = Self.merge(existing, node)
      } else {
        nodesByID[node.id] = node
      }
    }

    for edge in page.edges {
      if let existing = edgesByID[edge.id] {
        edgesByID[edge.id] = Self.merge(existing, edge)
      } else {
        edgesByID[edge.id] = edge
      }
    }

    if let catalogNodes = page.catalogNodes {
      if catalogNodesByID == nil { catalogNodesByID = [:] }
      for node in catalogNodes {
        if let existing = catalogNodesByID?[node.id] {
          catalogNodesByID?[node.id] = Self.merge(existing, node)
        } else {
          catalogNodesByID?[node.id] = node
        }
      }
    }

    if let count = page.eligibleItemCount {
      eligibleItemCount = max(eligibleItemCount ?? count, count)
    }
    if let count = page.processedItemCount {
      processedItemCount = max(processedItemCount ?? count, count)
    }
  }

  func response() -> KnowledgeGraphResponse {
    let nodes = nodesByID.values.sorted { $0.id < $1.id }
    let nodeIDs = Set(nodes.map(\.id))

    // A backend page may carry an edge before the page containing one of its
    // endpoints. Cleanup happens only after all pages have been accumulated.
    var edgesByRelationship: [KnowledgeGraphRelationship: KnowledgeGraphEdge] = [:]
    for edge in edgesByID.values where nodeIDs.contains(edge.sourceId) && nodeIDs.contains(edge.targetId) {
      let relationship = KnowledgeGraphRelationship(
        sourceId: edge.sourceId,
        targetId: edge.targetId,
        label: edge.label)
      if let existing = edgesByRelationship[relationship] {
        edgesByRelationship[relationship] = Self.merge(existing, edge)
      } else {
        edgesByRelationship[relationship] = edge
      }
    }

    let edges = edgesByRelationship.values.sorted(by: Self.edgePrecedes)
    return KnowledgeGraphResponse(
      nodes: nodes,
      edges: edges,
      eligibleItemCount: eligibleItemCount,
      processedItemCount: processedItemCount,
      catalogNodes: catalogNodesByID?.values.sorted { $0.id < $1.id })
  }

  private static func merge(_ lhs: KnowledgeGraphNode, _ rhs: KnowledgeGraphNode) -> KnowledgeGraphNode {
    KnowledgeGraphNode(
      id: lhs.id,
      label: min(lhs.label, rhs.label),
      nodeType: KnowledgeGraphNodeType(rawValue: min(lhs.nodeType.rawValue, rhs.nodeType.rawValue)) ?? .concept,
      aliases: Array(Set(lhs.aliases).union(rhs.aliases)).sorted(),
      memoryIds: Array(Set(lhs.memoryIds).union(rhs.memoryIds)).sorted(),
      createdAt: min(lhs.createdAt, rhs.createdAt),
      updatedAt: max(lhs.updatedAt, rhs.updatedAt))
  }

  private static func merge(_ lhs: KnowledgeGraphEdge, _ rhs: KnowledgeGraphEdge) -> KnowledgeGraphEdge {
    let canonical = edgePrecedes(lhs, rhs) ? lhs : rhs
    return KnowledgeGraphEdge(
      id: canonical.id,
      sourceId: canonical.sourceId,
      targetId: canonical.targetId,
      label: canonical.label,
      memoryIds: Array(Set(lhs.memoryIds).union(rhs.memoryIds)).sorted(),
      createdAt: min(lhs.createdAt, rhs.createdAt))
  }

  private static func edgePrecedes(_ lhs: KnowledgeGraphEdge, _ rhs: KnowledgeGraphEdge) -> Bool {
    if lhs.id != rhs.id { return lhs.id < rhs.id }
    if lhs.sourceId != rhs.sourceId { return lhs.sourceId < rhs.sourceId }
    if lhs.targetId != rhs.targetId { return lhs.targetId < rhs.targetId }
    if lhs.label != rhs.label { return lhs.label < rhs.label }
    if lhs.createdAt != rhs.createdAt { return lhs.createdAt < rhs.createdAt }
    return lhs.memoryIds.sorted().joined(separator: "\u{1f}")
      < rhs.memoryIds.sorted().joined(separator: "\u{1f}")
  }
}

private struct KnowledgeGraphRelationship: Hashable {
  let sourceId: String
  let targetId: String
  let label: String
}

/// Response for rebuild operation
struct RebuildGraphResponse: Codable {
  let status: String
  let nodesCount: Int?
  let edgesCount: Int?

  enum CodingKeys: String, CodingKey {
    case status
    case nodesCount = "nodes_count"
    case edgesCount = "edges_count"
  }
}

// MARK: - Knowledge Graph API

/// The backend's answer when this account has no canonical graph state at all.
/// Production fences canonical intake, so `/v1/knowledge-graph/canonical` gives
/// this to accounts whose graph only exists in the legacy store — a statement
/// about the account, not a transient outage. Any other 503 stays an outage.
private let canonicalGraphUnavailableDetail = "canonical_graph_unavailable"

extension APIClient {

  /// Gets the complete canonical graph, exhausting the bounded page endpoint.
  ///
  /// The endpoint was added after the legacy graph route, so a 404/405 on the
  /// canonical route selects the legacy request, as does a 503 that names this
  /// account as having no canonical state. Every other error is returned to the
  /// caller.
  func getKnowledgeGraphImpl(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KnowledgeGraphResponse {
    guard
      let pinnedAuthorization =
        authorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: expectedOwnerId)
    else {
      throw AuthError.userChangedDuringRequest
    }

    do {
      return try await getCanonicalKnowledgeGraph(
        expectedOwnerId: expectedOwnerId,
        authorizationSnapshot: pinnedAuthorization)
    } catch APIError.httpError(statusCode: let statusCode, detail: let detail)
      where statusCode == 404 || statusCode == 405
      || (statusCode == 503 && detail == canonicalGraphUnavailableDetail)
    {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "memory_atlas",
        from: "canonical_paged_graph",
        to: "legacy_graph",
        reason: statusCode == 503
          ? "canonical_state_unavailable_503"
          : "canonical_endpoint_unavailable_" + String(statusCode),
        outcome: .recovered
      )
      let legacy: KnowledgeGraphResponse = try await get(
        "v1/knowledge-graph",
        expectedOwnerId: expectedOwnerId,
        authorizationSnapshot: pinnedAuthorization)
      return KnowledgeGraphResponse.merged(pages: [legacy])
    }
  }

  /// Gets one canonical graph page. Callers needing the complete graph should
  /// use `getKnowledgeGraph()` so page accumulation remains sequential and
  /// publishes only after the final page has been received.
  func getKnowledgeGraphPageImpl(
    limit: Int = KnowledgeGraphResponse.defaultPageSize,
    cursor: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KnowledgeGraphResponse {
    let boundedLimit = min(max(limit, 1), KnowledgeGraphResponse.maximumPageSize)
    var components = URLComponents()
    components.path = "/v1/knowledge-graph/canonical"
    components.queryItems = [URLQueryItem(name: "limit", value: String(boundedLimit))]
    if let cursor {
      components.queryItems?.append(URLQueryItem(name: "cursor", value: cursor))
    }
    guard let path = components.string else { throw APIError.invalidResponse }
    let endpoint = String(path.dropFirst())
    return try await get(
      endpoint,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  private func getCanonicalKnowledgeGraph(
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KnowledgeGraphResponse {
    var accumulator = KnowledgeGraphAccumulator()
    var cursor: String?
    var seenCursors = Set<String>()

    while true {
      try Task.checkCancellation()
      let page = try await getKnowledgeGraphPageImpl(
        limit: KnowledgeGraphResponse.defaultPageSize,
        cursor: cursor,
        expectedOwnerId: expectedOwnerId,
        authorizationSnapshot: authorizationSnapshot)
      try Task.checkCancellation()
      accumulator.append(page)

      guard page.hasMore else { return accumulator.response() }
      guard let nextCursor = page.nextCursor,
        !nextCursor.isEmpty,
        nextCursor != cursor,
        seenCursors.insert(nextCursor).inserted
      else {
        throw APIError.invalidResponse
      }
      cursor = nextCursor
    }
  }

  /// Rebuild the knowledge graph from memories
  func rebuildKnowledgeGraphImpl(
    limit: Int = 500,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> RebuildGraphResponse {
    guard
      let pinnedAuthorization =
        authorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: expectedOwnerId)
    else {
      throw AuthError.userChangedDuringRequest
    }
    return try await post(
      "v1/knowledge-graph/rebuild?limit=\(limit)",
      body: EmptyBody(),
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: pinnedAuthorization)
  }

  /// Delete the knowledge graph
  func deleteKnowledgeGraphImpl() async throws {
    return try await delete("v1/knowledge-graph")
  }

  /// Return-only SSOT extraction through managed knowledge_graph (OpenRouter Luna).
  func extractKnowledgeGraphImpl(
    text: String,
    includeExisting: Bool = false,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KnowledgeGraphExtractResponse {
    guard
      let pinnedAuthorization =
        authorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: expectedOwnerId)
    else {
      throw AuthError.userChangedDuringRequest
    }
    struct Body: Encodable {
      let text: String
      let includeExisting: Bool
      enum CodingKeys: String, CodingKey {
        case text
        case includeExisting = "include_existing"
      }
    }
    return try await post(
      "v1/knowledge-graph/extract",
      body: Body(text: text, includeExisting: includeExisting),
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: pinnedAuthorization,
      requestTimeout: Self.managedSynthesisTimeout)
  }
}

struct KnowledgeGraphExtractResponse: Codable, Equatable, Sendable {
  let nodes: [KnowledgeGraphNode]
  let edges: [KnowledgeGraphEdge]
}
