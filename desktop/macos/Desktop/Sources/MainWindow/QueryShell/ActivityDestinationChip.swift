//
//  ActivityDestinationChip.swift — the Activity spine's chip row, and the door it now is.
//
//  Activity used to carry two stacked rows of chips: the Memory hub's switcher
//  (`Activity | Conversations | Memories | Brain Map`) and, directly beneath it, a filter row
//  (`All | Conversations | Memories | Tasks | Rewind`) that narrowed the spine in place. Two rows
//  that look alike, one word apart, doing different things is the ambiguity — you cannot tell from
//  the row which `Conversations` you are about to press.
//
//  So there is one row, and every chip in it navigates. That is the rule the row teaches and the
//  rule it keeps: no chip here narrows the list while its neighbour leaves the page. `Brain Map`
//  joins it because it is now a peer destination rather than a control hidden in the panel header.
//
//  **This value is the reachability claim, not decoration.** `ShellDestination.Reach.activityChipRow`
//  names this row as the mechanism that reaches Conversations, Memories and Brain Map now that the
//  switcher is gone, and `ShellDestination.unreachable()` checks membership here. The row's `ForEach`
//  and the invariant model therefore read the same list — a destination dropped from this enum is a
//  test failure rather than a page someone discovers is stranded.
//

import Foundation

/// One chip in Activity's row. Every case is a destination; none is a filter.
enum ActivityDestinationChip: String, CaseIterable, Identifiable {
  case activity
  case conversations
  case memories
  case brainMap

  var id: String { rawValue }

  var title: String {
    switch self {
    case .activity: return "Brain"
    case .conversations: return "Conversations"
    case .memories: return "Memories"
    case .brainMap: return "Brain Map"
    }
  }

  /// The Memory hub page this chip opens. Every chip in this row is one of the hub's four pages:
  /// `Tasks` and `Rewind` were here too and were removed, because each already has its own pill in
  /// the bar directly above — a second control to the same place, two inches apart.
  ///
  /// **Not optional, and that is the reachability claim's teeth.** A chip that opens no hub page
  /// would be a chip that reaches nothing while `reachableHubDestinations` quietly dropped it; the
  /// type forbids adding one rather than leaving a test to notice.
  var hubDestination: MemoryHubDestination {
    switch self {
    case .activity: return .activity
    case .conversations: return .conversations
    case .memories: return .memories
    case .brainMap: return .brainMap
    }
  }

  /// Every hub page this row can reach. `ShellDestination.unreachable()` reads exactly this.
  static var reachableHubDestinations: [MemoryHubDestination] {
    allCases.map(\.hubDestination)
  }
}
