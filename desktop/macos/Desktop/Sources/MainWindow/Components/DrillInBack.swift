import SwiftUI

/// A drill-in's way back, handed down to a page that is reused in more than one place.
///
/// Rewind is one page in the Brain hub, and also where a task's screen evidence or a Chat citation
/// lands. Opened that way it replaced the page the reader was on, so it owes them a `BackChip` to it
/// (docs/ux-contract.md §1). The page does not know how it was opened; the shell does, and puts this
/// in the environment only for that case. `nil` everywhere else, so the chip never appears on a
/// Rewind reached from its own tab.
struct DrillInBack {
  let title: String
  let action: @MainActor () -> Void
}

private struct DrillInBackKey: EnvironmentKey {
  static let defaultValue: DrillInBack? = nil
}

extension EnvironmentValues {
  var drillInBack: DrillInBack? {
    get { self[DrillInBackKey.self] }
    set { self[DrillInBackKey.self] = newValue }
  }
}
