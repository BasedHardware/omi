import CoreGraphics

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

/// Deterministic hover intent for the native Memory menu.
///
/// SwiftUI owns this value. AppKit only presents the menu when
/// `presentationRequest` advances, so crossing the navigation bar cannot open a
/// stale menu after the pointer has already left.
struct MemoryMenuHoverIntent: Equatable {
  private(set) var generation = 0
  private(set) var presentationRequest = 0

  mutating func hoverChanged(_ isHovering: Bool) -> Int? {
    generation += 1
    return isHovering ? generation : nil
  }

  @discardableResult
  mutating func openAfterHoverDelay(generation expectedGeneration: Int) -> Bool {
    guard generation == expectedGeneration else { return false }
    presentationRequest += 1
    return true
  }

  mutating func openImmediately() {
    generation += 1
    presentationRequest += 1
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
    transcriptDrawerOpen: Bool
  ) -> Bool {
    guard let conversationID else { return false }
    return transcriptDrawerOpen && conversationID == presentedConversationID
  }
}
