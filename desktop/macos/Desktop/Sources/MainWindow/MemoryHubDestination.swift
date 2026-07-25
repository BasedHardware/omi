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

  /// Resolves navigation into the Memory rail item. Existing callers such as
  /// Cmd+2 and desktop automation only know about the rail item, so they must
  /// land on Conversations instead of whichever Memory destination was last
  /// persisted.
  static func destination(
    for sidebarItem: SidebarNavItem,
    requestedRawValue: Int? = nil
  ) -> MemoryHubDestination? {
    guard sidebarItem == .conversations else { return nil }
    guard let requestedRawValue else { return .conversations }
    return MemoryHubDestination(rawValue: requestedRawValue) ?? .conversations
  }
}
