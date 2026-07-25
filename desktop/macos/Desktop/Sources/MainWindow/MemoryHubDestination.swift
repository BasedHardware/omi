/// Destinations available from the Memory navigation menu.
enum MemoryHubDestination: Int, CaseIterable, Identifiable {
  static let storageKey = "memoryHubDestination"

  case memories
  case conversations
  case brainMap

  var id: Int { rawValue }

  var title: String {
    switch self {
    case .memories: return "Memories"
    case .conversations: return "Conversations"
    case .brainMap: return "Brain Map"
    }
  }

  var icon: String {
    switch self {
    case .memories: return "brain.head.profile"
    case .conversations: return "text.bubble"
    case .brainMap: return "point.3.connected.trianglepath.dotted"
    }
  }
}
