import Foundation

/// Which release notes the Updates section is showing open, and how far down the list it has been
/// asked to go.
///
/// This is a model rather than `@State` on the pane for two reasons: the reader's place in the list
/// survives leaving Settings and coming back, and the automation bridge can drive and read the same
/// state a click drives, so the disclosure is testable end to end instead of only by eye.
@MainActor
final class ReleaseNotesDisclosure: ObservableObject {
  static let shared = ReleaseNotesDisclosure()

  /// How many more releases each "Show More" reveals, and how many show on arrival.
  static let pageSize = 5

  /// Older releases the reader has opened. The newest release is always open and never listed here.
  @Published private(set) var expandedVersions: Set<String> = []

  /// How many releases the list renders, oldest end trimmed.
  @Published private(set) var visibleCount: Int = ReleaseNotesDisclosure.pageSize

  init() {}

  func isExpanded(_ version: String, isNewest: Bool) -> Bool {
    isNewest || expandedVersions.contains(version)
  }

  /// Open or close one older release. The newest release cannot be closed — it is the reason the
  /// section exists, so its row is not a disclosure at all.
  func toggle(_ version: String, isNewest: Bool = false) {
    guard !isNewest else { return }
    if expandedVersions.contains(version) {
      expandedVersions.remove(version)
    } else {
      expandedVersions.insert(version)
    }
  }

  /// Reveal another page, never past the end of the list.
  func showMore(total: Int) {
    visibleCount = min(max(total, 0), visibleCount + Self.pageSize)
  }

  func canShowMore(total: Int) -> Bool {
    total > visibleCount
  }
}
