import XCTest

@testable import Omi_Computer

/// TASK-03: 150 reorders in one category → stable ordering, no sortOrder collision.
///
/// Live-account runs of this criterion are structurally racy: the store's paginated
/// bucket window (50/category on large accounts) evicts seeded tasks mid-run and the
/// dump then compares against rows the reorder never renumbered — the BL-046
/// "duplicate sortOrders" artifact. The product math itself is deterministic, so this
/// pins the criterion as a property test over the EXACT algorithm chain `moveTask`
/// uses per drag: the 3-line order-list mutation (removeAll → clamp → insert) followed
/// by `TasksViewModel.applyReorder` (which bands via the shared `sortOrder` helper).
/// 150 seeded-random reorders over 30 tasks; after EVERY step the invariants must
/// hold — uniqueness, band membership, and displayed-order agreement.
final class Task03ReorderStressTests: XCTestCase {

  private func item(_ id: String) -> TaskActionItem {
    TaskActionItem(
      id: id, description: id, completed: false,
      createdAt: Date(timeIntervalSince1970: 0), dueAt: nil, sortOrder: nil)
  }

  func test150RandomReordersKeepOrderingStableAndCollisionFree() {
    var rng = SystemRandomNumberGenerator.seeded(19)
    let categoryIndex = 3  // noDeadline band [300_000, 400_000)
    let ids = (1...30).map { "t\($0)" }
    var tasks = ids.map { item($0) }
    var order = ids

    for step in 1...150 {
      // The exact mutation moveTask performs on the category order list.
      let moved = ids[Int(rng.next() % 30)]
      let target = Int(rng.next() % 31)
      order.removeAll { $0 == moved }
      order.insert(moved, at: min(target, order.count))

      TasksViewModel.applyReorder(order, categoryIndex: categoryIndex, to: &tasks)

      let sortOrders = order.compactMap { id in tasks.first { $0.id == id }?.sortOrder }
      XCTAssertEqual(
        sortOrders.count, order.count,
        "step \(step): every task in the order list must carry a sortOrder")
      XCTAssertEqual(
        Set(sortOrders).count, sortOrders.count,
        "step \(step): sortOrders must be collision-free")
      XCTAssertEqual(
        sortOrders, sortOrders.sorted(),
        "step \(step): sortOrders must be monotonic with displayed position")
      XCTAssertTrue(
        sortOrders.allSatisfy { (300_000..<400_000).contains($0) },
        "step \(step): every sortOrder must stay inside the category band")
    }
  }

  func testReorderResultIsDeterministicForIdenticalMoveSequences() {
    // Same seed → same final ordering; the criterion's "stable ordering" half.
    func run() -> [Int?] {
      var rng = SystemRandomNumberGenerator.seeded(7)
      let ids = (1...30).map { "t\($0)" }
      var tasks = ids.map { item($0) }
      var order = ids
      for _ in 1...150 {
        let moved = ids[Int(rng.next() % 30)]
        let target = Int(rng.next() % 31)
        order.removeAll { $0 == moved }
        order.insert(moved, at: min(target, order.count))
        TasksViewModel.applyReorder(order, categoryIndex: 3, to: &tasks)
      }
      return order.map { id in tasks.first { $0.id == id }?.sortOrder }
    }
    XCTAssertEqual(run(), run(), "identical move sequences must produce identical orderings")
  }
}

/// Deterministic RNG so the 150-step sequence is reproducible across runs/machines.
/// (SystemRandomNumberGenerator itself is not seedable; this is a tiny SplitMix64.)
extension SystemRandomNumberGenerator {
  fileprivate static func seeded(_ seed: UInt64) -> SplitMix64 { SplitMix64(seed: seed) }
}

struct SplitMix64: RandomNumberGenerator {
  private var state: UInt64
  init(seed: UInt64) { state = seed }
  mutating func next() -> UInt64 {
    state &+= 0x9E37_79B9_7F4A_7C15
    var z = state
    z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
    z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
    return z ^ (z >> 31)
  }
}
