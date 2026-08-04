import CoreGraphics

/// Destinations available from the Memory navigation menu.
enum MemoryHubDestination: Int, CaseIterable, Identifiable {
  static let storageKey = "memoryHubDestination"
  static let dropdownDestinations: [MemoryHubDestination] = [.conversations, .brainMap]

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
}

/// Deterministic interaction state for the Memory dropdown.
///
/// The anchor and menu report hover independently so the pointer can cross the
/// small visual gap without dismissing the menu. Delayed transitions carry a
/// generation token so stale hover work cannot reopen or close the dropdown.
struct MemoryDropdownInteractionState: Equatable {
  enum HoverRegion {
    case anchor
    case dropdown
  }

  struct PendingPresentation: Equatable {
    let generation: Int
    let isPresented: Bool
  }

  private(set) var generation = 0
  private(set) var isPresented = false
  private var isAnchorHovered = false
  private var isDropdownHovered = false

  mutating func hoverChanged(
    _ isHovering: Bool,
    in region: HoverRegion
  ) -> PendingPresentation? {
    generation += 1
    switch region {
    case .anchor: isAnchorHovered = isHovering
    case .dropdown: isDropdownHovered = isHovering
    }

    let shouldPresent = isAnchorHovered || isDropdownHovered
    guard shouldPresent != isPresented else { return nil }
    return PendingPresentation(generation: generation, isPresented: shouldPresent)
  }

  @discardableResult
  mutating func apply(_ pendingPresentation: PendingPresentation) -> Bool {
    guard generation == pendingPresentation.generation else { return false }
    isPresented = pendingPresentation.isPresented
    return true
  }

  mutating func dismiss() {
    generation += 1
    isPresented = false
    isAnchorHovered = false
    isDropdownHovered = false
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
