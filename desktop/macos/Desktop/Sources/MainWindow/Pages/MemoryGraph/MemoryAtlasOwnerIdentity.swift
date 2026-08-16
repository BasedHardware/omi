import Foundation

enum MemoryAtlasOwnerIdentity {
  struct Resolution {
    let anchor: KnowledgeGraphNode?
    let isSynthetic: Bool
  }

  private static let selfSynonyms: Set<String> = ["user", "me", "myself", "i", "the user"]

  static func isSelfNode(_ node: KnowledgeGraphNode) -> Bool {
    node.id == "user" || selfSynonyms.contains(node.label.lowercased())
      || node.aliases.contains { selfSynonyms.contains($0.lowercased()) }
  }

  static func resolve(nodes: [KnowledgeGraphNode], userName: String?) -> Resolution {
    let profileName = userName?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let profileMatches = nodes.filter {
      profileName != nil && $0.nodeType == .person
        && ($0.label.lowercased() == profileName || $0.aliases.contains { $0.lowercased() == profileName })
    }
    if let node = profileMatches.count == 1 ? profileMatches[0] : nil {
      return Resolution(anchor: node, isSynthetic: false)
    }
    if let node = nodes.first(where: { $0.id == "user" }) ?? nodes.first(where: isSelfNode) {
      return Resolution(anchor: node, isSynthetic: false)
    }
    guard let userName, !userName.isEmpty else { return Resolution(anchor: nil, isSynthetic: false) }
    return Resolution(
      anchor: KnowledgeGraphNode(id: "atlas-owner", label: userName, nodeType: .person),
      isSynthetic: true
    )
  }
}
