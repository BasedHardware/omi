import SwiftUI

/// The onboarding welcome graph, populated from the user's REAL knowledge graph
/// (the same source the Brain map page uses) — never fake sample nodes. If the
/// graph is still empty (a brand-new account), it shows an honest "starts empty"
/// state instead of inventing entries.
struct RedesignLiveBrainGraph: View {
  @StateObject private var loader = OnboardingGraphLoader()

  private var coreLabel: String {
    let given = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    return given.isEmpty ? "omi" : given
  }

  var body: some View {
    Group {
      if !loader.loaded {
        // brief neutral state while the real graph loads
        RedesignBrainGraph(nodes: [RedesignBrainNode(text: coreLabel, x: 0.5, y: 0.46, core: true)])
      } else if loader.labels.isEmpty {
        emptyState
      } else {
        RedesignBrainGraph(
          nodes: buildNodes(loader.labels), links: buildLinks(loader.labels.count))
      }
    }
    .task { await loader.load() }
  }

  private func buildNodes(_ labels: [String]) -> [RedesignBrainNode] {
    var nodes: [RedesignBrainNode] = [RedesignBrainNode(text: coreLabel, x: 0.5, y: 0.46, core: true)]
    let n = max(1, labels.count)
    for (i, label) in labels.enumerated() {
      let angle = Double(i) / Double(n) * 2 * .pi - .pi / 2
      let x = 0.5 + cos(angle) * 0.34
      let y = 0.46 + sin(angle) * 0.36
      nodes.append(RedesignBrainNode(text: label, x: x, y: y))
    }
    return nodes
  }

  private func buildLinks(_ count: Int) -> [(Int, Int)] {
    guard count > 0 else { return [] }
    return (1...count).map { (0, $0) }
  }

  private var emptyState: some View {
    ZStack {
      RedesignBrainGraph(nodes: [RedesignBrainNode(text: coreLabel, x: 0.5, y: 0.42, core: true)])
      VStack {
        Spacer()
        Text("It starts empty. I'll fill this in as I read your week.")
          .font(InkFont.sans(12.5))
          .foregroundColor(Ink.faint)
          .padding(.bottom, 48)
      }
    }
  }
}

@MainActor
final class OnboardingGraphLoader: ObservableObject {
  @Published var labels: [String] = []
  @Published var loaded = false

  func load() async {
    let response = await KnowledgeGraphStorage.shared.loadGraph()
    let userName = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces).lowercased()
    let ranked =
      response.nodes
      .filter { !$0.label.trimmingCharacters(in: .whitespaces).isEmpty }
      // don't duplicate the user's own node as a satellite
      .filter { $0.label.trimmingCharacters(in: .whitespaces).lowercased() != userName }
      .sorted { $0.memoryIds.count > $1.memoryIds.count }
    labels = Array(ranked.prefix(6).map { $0.label })
    loaded = true
  }
}
