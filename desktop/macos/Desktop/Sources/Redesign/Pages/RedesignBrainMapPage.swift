import SwiftUI

/// Brain map — the knowledge-graph view, light-wired. Mockup `memory-graph.html`.
///
/// A calm 2D constellation: a central ink node (you) with your real knowledge-graph
/// entities — people, projects, goals, ideas — arranged around it and joined by hairline
/// connectors. Data comes from the same source the SceneKit `MemoryGraphViewModel` uses
/// (`KnowledgeGraphStorage.shared` with an `APIClient.shared.getKnowledgeGraph()` fallback);
/// that view model keeps its nodes private for the 3D simulation, so this page reads the
/// raw graph directly to render labels + connections in 2D.
///
/// Constructed in `DesktopHomeView.PageContentView` as `RedesignBrainMapPage(selectedIndex: $selectedTabIndex)`.
struct RedesignBrainMapPage: View {
  @StateObject private var model = RedesignBrainMapModel()
  @Binding var selectedIndex: Int
  @State private var selectedNodeID: String?

  init(selectedIndex: Binding<Int>) {
    self._selectedIndex = selectedIndex
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        header

        if model.isLoading && model.nodes.isEmpty {
          loadingState
        } else if model.nodes.isEmpty {
          emptyState
        } else {
          graphCard
          caption
        }
      }
      .frame(maxWidth: 900, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .task {
      await model.loadIfNeeded()
    }
  }

  // MARK: - Header

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 8) {
        Text("Second brain").inkEyebrow()
        Text("Everything I’ve learned, connected.").inkH1()
      }
      Spacer()
      InkButton(title: "Back to memory", systemImage: "chevron.left", kind: .ghost, size: .sm) {
        selectedIndex = 3  // Memory
      }
      .padding(.top, 4)
    }
    .padding(.bottom, 4)
  }

  // MARK: - Graph

  private var graphCard: some View {
    GeometryReader { geo in
      let layout = BrainLayout(
        size: geo.size,
        center: model.centerLabel,
        nodes: model.displayNodes,
        edges: model.displayEdges
      )

      ZStack {
        // Hairline connectors — spokes from the center + real inter-node edges.
        Canvas { ctx, _ in
          // Real edges between displayed entities (fainter).
          for link in layout.interLinks {
            var p = Path()
            p.move(to: link.0)
            p.addLine(to: link.1)
            ctx.stroke(p, with: .color(Ink.ink.opacity(0.05)), lineWidth: 1)
          }
          // Spokes: center → each entity.
          for point in layout.points {
            var p = Path()
            p.move(to: layout.centerPoint)
            p.addLine(to: point.position)
            ctx.stroke(p, with: .color(Ink.ink.opacity(0.10)), lineWidth: 1)
          }
        }

        // Surrounding entity pills.
        ForEach(layout.points) { point in
          nodePill(point)
            .position(point.position)
        }

        // Central ink "you" node.
        coreNode(layout.center)
          .position(layout.centerPoint)
      }
      .overlay(alignment: .bottomLeading) {
        if let id = selectedNodeID, let detail = model.detail(for: id) {
          nodeDetail(detail)
            .padding(12)
            .transition(.opacity)
        }
      }
    }
    .frame(height: 520)
    .frame(maxWidth: .infinity)
    .background(
      RoundedRectangle(cornerRadius: InkRadius.card, style: .continuous)
        .fill(Ink.soft)
    )
    .overlay(
      RoundedRectangle(cornerRadius: InkRadius.card, style: .continuous)
        .stroke(Ink.hair, lineWidth: 1)
    )
  }

  private func coreNode(_ label: String) -> some View {
    Text(label)
      .font(InkFont.sans(13, .semibold))
      .foregroundColor(Ink.accentInk)
      .lineLimit(1)
      .padding(.horizontal, 14)
      .padding(.vertical, 9)
      .background(
        Capsule().fill(Ink.accent)
      )
      .shadow(color: Ink.ink.opacity(0.18), radius: 10, x: 0, y: 4)
  }

  private func nodePill(_ point: BrainPoint) -> some View {
    Button {
      withAnimation(.easeOut(duration: 0.15)) {
        selectedNodeID = (selectedNodeID == point.id) ? nil : point.id
      }
    } label: {
      Text(point.label)
        .font(InkFont.sans(12.5, .regular))
        .foregroundColor(point.dim ? Ink.muted : Ink.ink)
        .lineLimit(1)
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(
          Capsule().fill(Ink.surface)
        )
        .overlay(
          Capsule().stroke(
            selectedNodeID == point.id ? Ink.ink.opacity(0.55) : Ink.hair2,
            lineWidth: selectedNodeID == point.id ? 1.5 : 1)
        )
        .shadow(color: Ink.ink.opacity(0.06), radius: 8, x: 0, y: 2)
    }
    .buttonStyle(.plain)
  }

  private func nodeDetail(_ detail: BrainNodeDetail) -> some View {
    InkCard(padding: 14, radius: 12) {
      VStack(alignment: .leading, spacing: 6) {
        HStack(spacing: 8) {
          Text(detail.label)
            .font(InkFont.sans(14, .semibold))
            .foregroundColor(Ink.ink)
          Spacer(minLength: 12)
          Button {
            withAnimation(.easeOut(duration: 0.15)) { selectedNodeID = nil }
          } label: {
            Image(systemName: "xmark")
              .font(.system(size: 10, weight: .semibold))
              .foregroundColor(Ink.faint)
          }
          .buttonStyle(.plain)
        }
        Text(detail.subtitle)
          .font(InkFont.sans(12))
          .foregroundColor(Ink.muted)
        if !detail.connections.isEmpty {
          Text("Connected to " + detail.connections.prefix(4).joined(separator: ", "))
            .font(InkFont.sans(12))
            .foregroundColor(Ink.body)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
    }
    .frame(maxWidth: 280, alignment: .leading)
  }

  private var caption: some View {
    Text("Tap a node to explore · \(model.memoriesText) · \(model.peopleText)")
      .inkCaption()
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.top, 2)
  }

  // MARK: - Empty / loading

  private var loadingState: some View {
    VStack(spacing: 14) {
      BuddyRing(diameter: 56, dot: 7, color: Ink.ink)
      Text("Reading your graph…").inkSmall()
    }
    .frame(maxWidth: .infinity, minHeight: 420, alignment: .center)
  }

  private var emptyState: some View {
    VStack(spacing: 16) {
      BuddyRing(diameter: 60, dot: 8, color: Ink.ink)
      VStack(spacing: 6) {
        Text("Your brain map is still forming.")
          .font(InkFont.serif(20, .regular))
          .foregroundColor(Ink.ink)
        Text("As I learn about your people, projects and ideas, they’ll connect here.")
          .inkSmall()
          .multilineTextAlignment(.center)
          .frame(maxWidth: 380)
      }
      if model.isRebuilding {
        Text("Building…").inkCaption()
      } else {
        InkButton(title: "Build it now", kind: .plain, size: .sm) {
          Task { await model.rebuild() }
        }
      }
    }
    .frame(maxWidth: .infinity, minHeight: 420, alignment: .center)
  }
}

// MARK: - Layout

private struct BrainPoint: Identifiable {
  let id: String
  let label: String
  let position: CGPoint
  let dim: Bool
}

private struct BrainLayout {
  let centerPoint: CGPoint
  let center: String
  let points: [BrainPoint]
  /// Real edges among the displayed nodes, resolved to pixel endpoints.
  let interLinks: [(CGPoint, CGPoint)]

  init(size: CGSize, center: String, nodes: [BrainDisplayNode], edges: [KnowledgeGraphEdge]) {
    self.center = center
    let cx = size.width / 2
    let cy = size.height / 2
    self.centerPoint = CGPoint(x: cx, y: cy)

    let rx = max(120, (size.width / 2) - 120)
    let ry = max(90, (size.height / 2) - 70)
    let count = max(nodes.count, 1)

    var pts: [BrainPoint] = []
    var positionByID: [String: CGPoint] = [:]
    for (i, node) in nodes.enumerated() {
      // Even spread with a phase offset; alternate two rings so labels don't collide.
      let angle = (2 * Double.pi * Double(i) / Double(count)) - Double.pi / 2
      let ring: Double = (i % 2 == 0) ? 1.0 : 0.72
      let x = cx + CGFloat(cos(angle)) * rx * CGFloat(ring)
      let y = cy + CGFloat(sin(angle)) * ry * CGFloat(ring)
      let pos = CGPoint(x: x, y: y)
      positionByID[node.id] = pos
      pts.append(BrainPoint(id: node.id, label: node.label, position: pos, dim: node.dim))
    }
    self.points = pts

    var links: [(CGPoint, CGPoint)] = []
    for edge in edges {
      guard let a = positionByID[edge.sourceId], let b = positionByID[edge.targetId] else { continue }
      links.append((a, b))
    }
    self.interLinks = links
  }
}

private struct BrainDisplayNode {
  let id: String
  let label: String
  let dim: Bool
}

struct BrainNodeDetail {
  let label: String
  let subtitle: String
  let connections: [String]
}

// MARK: - Model

/// Reads the real knowledge graph (local store first, backend fallback) and exposes the
/// most-connected entities for a radial 2D render around the signed-in user.
@MainActor
final class RedesignBrainMapModel: ObservableObject {
  @Published private(set) var nodes: [KnowledgeGraphNode] = []
  @Published private(set) var edges: [KnowledgeGraphEdge] = []
  @Published private(set) var isLoading = false
  @Published private(set) var isRebuilding = false

  private var hasLoaded = false
  private let maxNodes = 12

  var centerLabel: String {
    let name = AuthService.shared.givenName
    return name.isEmpty ? "You" : name
  }

  // Entities to draw: the highest-degree nodes (most connected feel most central).
  private var topNodes: [KnowledgeGraphNode] {
    let degree = nodeDegrees()
    return nodes.sorted { (degree[$0.id] ?? 0) > (degree[$1.id] ?? 0) }
      .prefix(maxNodes)
      .map { $0 }
  }

  fileprivate var displayNodes: [BrainDisplayNode] {
    let degree = nodeDegrees()
    let top = topNodes
    // Below-median degree renders "dim" (muted) like the mockup's faint nodes.
    let median = top.map { degree[$0.id] ?? 0 }.sorted()[safe: top.count / 2] ?? 0
    return top.map {
      BrainDisplayNode(id: $0.id, label: $0.label, dim: (degree[$0.id] ?? 0) < median)
    }
  }

  var displayEdges: [KnowledgeGraphEdge] {
    let ids = Set(topNodes.map { $0.id })
    return edges.filter { ids.contains($0.sourceId) && ids.contains($0.targetId) }
  }

  var memoriesText: String {
    let unique = Set(nodes.flatMap { $0.memoryIds }).count
    let n = unique > 0 ? unique : nodes.count
    return "\(formatted(n)) \(n == 1 ? "memory" : "memories")"
  }

  var peopleText: String {
    let n = nodes.filter { $0.nodeType == .person }.count
    return "\(formatted(n)) \(n == 1 ? "person" : "people")"
  }

  func loadIfNeeded() async {
    guard !hasLoaded else { return }
    hasLoaded = true
    await load()
  }

  func load() async {
    isLoading = true
    defer { isLoading = false }
    let response = await fetchGraph()
    nodes = response.nodes
    edges = response.edges
  }

  func rebuild() async {
    isRebuilding = true
    defer { isRebuilding = false }
    do {
      _ = try await APIClient.shared.rebuildKnowledgeGraph()
      try? await Task.sleep(nanoseconds: 2_000_000_000)
    } catch {
      log("RedesignBrainMap: rebuild failed: \(error.localizedDescription)")
    }
    await load()
  }

  func detail(for id: String) -> BrainNodeDetail? {
    guard let node = nodes.first(where: { $0.id == id }) else { return nil }
    let memCount = node.memoryIds.count
    var subtitleParts: [String] = [node.nodeType.displayName]
    if memCount > 0 {
      subtitleParts.append("\(memCount) \(memCount == 1 ? "memory" : "memories")")
    }
    // Neighbor labels from real edges.
    var neighborIDs = Set<String>()
    for edge in edges {
      if edge.sourceId == id { neighborIDs.insert(edge.targetId) }
      if edge.targetId == id { neighborIDs.insert(edge.sourceId) }
    }
    let connections = nodes.filter { neighborIDs.contains($0.id) }.map { $0.label }
    return BrainNodeDetail(
      label: node.label,
      subtitle: subtitleParts.joined(separator: " · "),
      connections: connections)
  }

  // MARK: - Private

  /// Mirrors `MemoryGraphViewModel.fetchGraph`: prefer the local store, fall back to the API.
  private func fetchGraph() async -> KnowledgeGraphResponse {
    let local = await KnowledgeGraphStorage.shared.loadGraph()
    if !local.nodes.isEmpty { return local }

    if AuthState.shared.isSignedIn {
      do {
        return try await APIClient.shared.getKnowledgeGraph()
      } catch {
        log("RedesignBrainMap: getKnowledgeGraph failed: \(error.localizedDescription)")
      }
    }
    return local
  }

  private func nodeDegrees() -> [String: Int] {
    var degree: [String: Int] = [:]
    for edge in edges {
      degree[edge.sourceId, default: 0] += 1
      degree[edge.targetId, default: 0] += 1
    }
    return degree
  }

  private func formatted(_ n: Int) -> String {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    return f.string(from: NSNumber(value: n)) ?? "\(n)"
  }
}

private extension Array {
  subscript(safe index: Int) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}
