import CoreGraphics

/// Destinations available from the Memory navigation menu.
enum MemoryHubDestination: Int, CaseIterable, Identifiable {
  static let storageKey = "memoryHubDestination"

  /// The order the hub's own switcher reads in: the thing you captured, what Omi kept from it, then
  /// the map over all of it. Declared here rather than inside the switcher view so it stays a plain
  /// value a test can read without hopping to the main actor.
  ///
  /// `allCases` is *not* this order — its raw values are storage identity and start at `memories`,
  /// which is where the persisted default lands, not where the row should start.
  static let switcherOrder: [MemoryHubDestination] = [.activity, .conversations, .memories, .brainMap]

  case memories
  case conversations
  case brainMap
  /// The chronological spine that used to be Home's landing surface — everything captured, in the
  /// order it happened. Home now lands in the chat; the timeline lives here.
  case activity

  enum Presentation: Equatable {
    case standaloneConversations
    case memoryHub
  }

  var id: Int { rawValue }

  var title: String {
    switch self {
    case .memories: return "Memories"
    case .conversations: return "Conversations"
    case .brainMap: return "Brain Map"
    case .activity: return "Activity"
    }
  }

  var icon: String {
    switch self {
    case .memories: return "brain.head.profile"
    case .conversations: return "text.bubble"
    case .brainMap: return "point.3.connected.trianglepath.dotted"
    case .activity: return "clock.arrow.circlepath"
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

  static func applySidebarSelection(
    _ item: SidebarNavItem,
    selectedIndex: inout Int,
    memoryDestinationRawValue: inout Int
  ) {
    if let destination = destination(for: item) {
      memoryDestinationRawValue = destination.rawValue
    }
    selectedIndex = item.rawValue
  }

  /// The legacy sidebar has separate Conversations and Memories destinations.
  /// The modern top bar uses the same rail index as a Memory hub, so keep that
  /// shared index from replacing the old standalone Conversations page.
  static func presentation(
    for sidebarItem: SidebarNavItem,
    useLegacyHomeDesign: Bool
  ) -> Presentation {
    if useLegacyHomeDesign, sidebarItem == .conversations {
      return .standaloneConversations
    }
    return .memoryHub
  }
}

/// Shared readable-width contract for Memory surfaces.
///
/// Lists stay as calm and scannable as Tasks. A conversation expands only when
/// its transcript drawer is actually visible and needs the additional space.
enum MemoryHubLayoutPolicy {
  static let readableContentWidth: CGFloat = 900

  static func usesAvailableWidth(
    conversationID: String?,
    presentedConversationID: String?,
    transcriptDrawerOpen: Bool,
    memoryDetailOpen: Bool = false
  ) -> Bool {
    // A memory opened into the side inspector needs the same extra width a
    // transcript drawer does: the list keeps its readable column and the panel
    // takes the space beside it instead of squeezing the list.
    if memoryDetailOpen { return true }
    guard let conversationID else { return false }
    return transcriptDrawerOpen && conversationID == presentedConversationID
  }
}
