//
//  MemoryVisibilityGuardrails.swift — which memories a surface is allowed to show, in one place.
//
//  **This exists because the policy used to live inside one page's private recompute.** The archive
//  and device-scope rules were two `if` blocks in `MemoriesViewModel.recomputeFilteredMemories()`,
//  which meant they applied to exactly one array: the Memories page's own visible list. Every other
//  reader of the view model saw `memories` — the raw accumulation — and silently obeyed neither.
//
//  That is not a hypothetical. Home's chronological spine read `memories` and put **archived**
//  memories on the timeline, on a surface whose whole claim is that it shows you your day. The rule
//  was written down, tested, and correct; it was simply unreachable from a second call site.
//
//  So the fix is ownership, not another filter at the leak: the policy is a value here, both
//  projections run through it, and a third reader cannot get it wrong by forgetting to copy two
//  `if` statements. The device predicate is passed in rather than read here, which keeps this a pure
//  function of its inputs — a test states the answer instead of standing up a device service.
//

import Foundation

extension MemoryPageProjection {
  /// Apply the two guardrails every memory surface owes the user.
  ///
  /// - Parameters:
  ///   - allowedLayers: the tiers this view may show, or `nil` when the account has no canonical
  ///     lifecycle and every row is fair game. **Archive is never in the default list** — it is
  ///     reachable only by explicitly selecting it, because an archived memory is one the user has
  ///     already decided they do not want in front of them.
  ///   - thisDeviceOnly: whether the user has scoped the view to this Mac.
  ///   - deviceScopeSupported: whether the backend can answer that question for this account. When
  ///     it cannot, the scope is **not** applied locally: a canonical response is already filtered
  ///     server-side and its provenance is authoritative, while legacy rows cannot identify their
  ///     capture device at all. Filtering those client-side would empty the list and blame the user's
  ///     filter for it, which is a worse answer than showing them.
  ///   - matchesThisDevice: whether one memory was captured on this Mac.
  static func guardrailed(
    _ memories: [ServerMemory],
    allowedLayers: [MemoryLayer]?,
    thisDeviceOnly: Bool,
    deviceScopeSupported: Bool,
    matchesThisDevice: (ServerMemory) -> Bool
  ) -> [ServerMemory] {
    var result = memories
    if let allowedLayers {
      let allowed = Set(allowedLayers)
      result = result.filter { allowed.contains($0.tier) }
    }
    if thisDeviceOnly, deviceScopeSupported {
      result = result.filter(matchesThisDevice)
    }
    return result
  }
}
