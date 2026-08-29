import CoreGraphics

/// Destinations available from the Memory navigation menu.
enum MemoryHubDestination: Int, CaseIterable, Identifiable {
  static let storageKey = "memoryHubDestination"

  /// `allCases` is storage identity, not reading order: the raw values are persisted, so this list
  /// starts at `memories` — where the stored default lands — rather than where the user's row
  /// starts. The order the five pages are *presented* in belongs to the control that presents them,
  /// `ActivityDestinationChip`.
  case memories
  case conversations
  case brainMap
  /// The chronological spine that used to be Home's landing surface — everything captured, in the
  /// order it happened. Home now lands in the chat; the timeline lives here.
  case activity
  /// The visual screen-history player. Appended to preserve every persisted raw value above.
  case rewind

  var id: Int { rawValue }

  var title: String {
    switch self {
    case .memories: return "Memories"
    case .conversations: return "Conversations"
    case .brainMap: return "Brain Map"
    case .activity: return "Activity"
    case .rewind: return "Rewind"
    }
  }

  var icon: String {
    switch self {
    case .memories: return "brain.head.profile"
    case .conversations: return "text.bubble"
    case .brainMap: return "point.3.connected.trianglepath.dotted"
    case .activity: return "clock.arrow.circlepath"
    case .rewind: return "clock.arrow.circlepath"
    }
  }

  /// Resolves legacy navigation names into the one Memory hub. The raw sidebar
  /// index may differ, but Conversations, Memories, and Rewind must always
  /// select the same hub-owned presentation used by the modern shell.
  static func destination(for sidebarItem: SidebarNavItem) -> MemoryHubDestination? {
    switch sidebarItem {
    case .conversations:
      return .conversations
    case .memories:
      return .memories
    case .rewind:
      return .rewind
    default:
      return nil
    }
  }

  static func apply(
    _ item: SidebarNavItem,
    to selectedIndex: inout Int,
    hub memoryDestinationRawValue: inout Int
  ) {
    if let destination = destination(for: item) {
      memoryDestinationRawValue = destination.rawValue
    }
    selectedIndex = item.rawValue
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

/// How a hub selection is applied, per shell.
///
/// The chat-first shell keeps a typed route beside the persisted hub destination, so selecting a hub
/// view has to move both or the shell renders one view while claiming to be on another — which is the
/// state that made Brain Map unreachable from its Conversations route.
enum MemoryHubSelectionPolicy {
  /// The chat-first route that must be selected for a hub destination.
  ///
  /// Every Brain section uses the Memory route so the persistent section navigation remains
  /// mounted. Conversation deep links carry their record as focus state on that same route.
  static func chatFirstRoute(for destination: MemoryHubDestination) -> ChatFirstRoute {
    .memories
  }
}
