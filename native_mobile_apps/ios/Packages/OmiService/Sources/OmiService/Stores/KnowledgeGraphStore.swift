import Foundation
import Observation
import OmiNetwork

/// The memory graph (Flutter `memory_graph_page`): people, places and things Omi knows, linked
/// to the user at the center. Laid out once per load with a small force simulation.
@MainActor
@Observable
public final class KnowledgeGraphStore {
    public enum Phase: Equatable, Sendable { case idle, loading, loaded, failed }

    public struct PlacedNode: Identifiable, Sendable, Equatable {
        public let node: KnowledgeGraph.Node
        /// -1…1 on both axes; the user sits at (0, 0).
        public let x: Double
        public let y: Double
        public let isUser: Bool
        public var id: String { node.id }
    }

    public private(set) var phase: Phase = .idle
    public private(set) var nodes: [PlacedNode] = []
    public private(set) var edges: [KnowledgeGraph.Edge] = []

    private let api: any APIClientProtocol
    private let userName: String?

    public init(api: any APIClientProtocol, userName: String?) {
        self.api = api
        self.userName = userName
    }

    /// Nothing besides the user yet.
    public var isEmpty: Bool {
        !nodes.contains { !$0.isUser }
    }

    /// Who is connected to `id`, for highlighting a tapped node.
    public func neighbors(of id: String) -> Set<String> {
        Set(edges.compactMap { $0.source == id ? $0.target : $0.target == id ? $0.source : nil })
    }

    public func load() async {
        if nodes.isEmpty { phase = .loading }
        do {
            let graph = GraphLayout.centered(on: userName, try await api.knowledgeGraph())
            let positions = await Task.detached(priority: .userInitiated) {
                GraphLayout.positions(for: graph, center: GraphLayout.userID)
            }.value
            nodes = graph.nodes.map { node in
                let point = positions[node.id] ?? (0, 0)
                return PlacedNode(node: node, x: point.0, y: point.1, isUser: node.id == GraphLayout.userID)
            }
            edges = graph.edges
            phase = .loaded
        } catch {
            phase = .failed
        }
    }
}

/// Graph shaping and a deterministic 2D force layout (Flutter uses a 3D one; flat reads better here).
public enum GraphLayout {
    public static let userID = "user-node"

    /// Merges every node that stands for the user (type `user`, label "me" / "the user" / their
    /// name) into one center node, adding it when missing, and repoints its edges.
    public static func centered(on userName: String?, _ graph: KnowledgeGraph) -> KnowledgeGraph {
        let names = Set(["me", "the user", "user", userName?.lowercased()].compactMap(\.self))
        let userNodes = Set(graph.nodes.filter { $0.kind == "user" || names.contains($0.label.lowercased()) }.map(\.id))
        let label = graph.nodes.first { userNodes.contains($0.id) && $0.kind != "user" }?.label ?? userName ?? "You"
        var unique = Set<String>()
        let others = graph.nodes.filter { !userNodes.contains($0.id) && unique.insert($0.id).inserted }
        var seen = Set<String>()
        let edges = graph.edges.compactMap { edge -> KnowledgeGraph.Edge? in
            let source = userNodes.contains(edge.source) ? userID : edge.source
            let target = userNodes.contains(edge.target) ? userID : edge.target
            guard source != target, seen.insert([source, target].sorted().joined(separator: "|")).inserted else { return nil }
            return KnowledgeGraph.Edge(source: source, target: target, label: edge.label)
        }
        return KnowledgeGraph(nodes: [KnowledgeGraph.Node(id: userID, label: label, kind: "user")] + others, edges: edges)
    }

    /// Positions in -1…1. Nodes start on a golden-angle spiral (stable across loads), then repel each
    /// other while edges pull linked nodes together; `center` stays fixed at the origin.
    public static func positions(for graph: KnowledgeGraph, center: String) -> [String: (Double, Double)] {
        let ids = graph.nodes.map(\.id)
        let count = ids.count
        guard count > 1 else { return Dictionary(ids.map { ($0, (0.0, 0.0)) }, uniquingKeysWith: { first, _ in first }) }
        let index = Dictionary(ids.enumerated().map { ($1, $0) }, uniquingKeysWith: { first, _ in first })
        let links = graph.edges.compactMap { edge in index[edge.source].flatMap { s in index[edge.target].map { (s, $0) } } }
        let fixed = index[center]
        var x = [Double](repeating: 0, count: count), y = x
        for i in 0 ..< count where i != fixed {
            let radius = 0.2 + 0.8 * (Double(i) / Double(count)).squareRoot()
            x[i] = radius * cos(Double(i) * 2.399963)
            y[i] = radius * sin(Double(i) * 2.399963)
        }
        let ideal = 1.2 / Double(count).squareRoot()
        let steps = count > 150 ? 80 : 240
        for step in 0 ..< steps {
            let cooling = 0.08 * (1 - Double(step) / Double(steps))
            var fx = [Double](repeating: 0, count: count), fy = fx
            for a in 0 ..< count {
                for b in (a + 1) ..< count {
                    let dx = x[a] - x[b], dy = y[a] - y[b]
                    let distance = max((dx * dx + dy * dy).squareRoot(), 0.01)
                    let push = ideal * ideal / (distance * distance)
                    fx[a] += dx * push; fy[a] += dy * push
                    fx[b] -= dx * push; fy[b] -= dy * push
                }
            }
            for (s, t) in links {
                let dx = x[s] - x[t], dy = y[s] - y[t]
                let pull = (dx * dx + dy * dy).squareRoot() / ideal
                fx[s] -= dx * pull; fy[s] -= dy * pull
                fx[t] += dx * pull; fy[t] += dy * pull
            }
            for i in 0 ..< count where i != fixed {
                let length = max((fx[i] * fx[i] + fy[i] * fy[i]).squareRoot(), 0.0001)
                let move = min(length, cooling)
                x[i] += fx[i] / length * move
                y[i] += fy[i] / length * move
            }
        }
        let extent = max(zip(x, y).map { max(abs($0), abs($1)) }.max() ?? 1, 0.001)
        return Dictionary(ids.enumerated().map { ($1, (x[$0] / extent, y[$0] / extent)) }, uniquingKeysWith: { first, _ in first })
    }
}
