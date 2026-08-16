import Foundation

/// One validated cross-bucket fact quoted into the director's related-workstream
/// section. Deliberately carries no citable ref: pooled facts are advisory
/// context, and grounding stays on the visited bucket's own entries and facts.
struct ContextWorkstreamPoolItem: Equatable, Sendable {
  let factID: String
  let bucketID: String
  let appName: String
  let statement: String
  let notifyWorthiness: Double
  let createdAt: Date
}

/// Workstream labels are model-proposed once per fact at extraction time and
/// then behave as durable routing data, so everything stored must survive this
/// sanitizer. Failing to nil is always the safe direction: an untagged fact
/// simply never pools, exactly like every fact written before the tag existed.
enum ContextWorkstreamTag {
  /// The extraction prompt tells the model to answer this when unsure; it is an
  /// abstention, not a label.
  static let abstention = "unknown"
  static let maximumLength = 32

  static func sanitize(_ proposed: String?) -> String? {
    guard let proposed else { return nil }
    let lowered = proposed.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !lowered.isEmpty, lowered != abstention else { return nil }
    // Kebab-case identity: spaces and underscores collapse to hyphens, anything
    // outside [a-z0-9-] is dropped, and hyphen runs collapse so near-identical
    // proposals ("Omi App", "omi_app", "omi-app") converge on one tag.
    var kebab = ""
    for scalar in lowered.unicodeScalars {
      if scalar == " " || scalar == "_" || scalar == "-" {
        kebab.append("-")
      } else if (scalar >= "a" && scalar <= "z") || (scalar >= "0" && scalar <= "9") {
        kebab.append(Character(scalar))
      }
    }
    while kebab.contains("--") { kebab = kebab.replacingOccurrences(of: "--", with: "-") }
    kebab = kebab.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    guard kebab.count >= 2, kebab.count <= maximumLength else { return nil }
    guard kebab != abstention else { return nil }
    return kebab
  }
}

/// Pure selection policy for the related-workstream prompt section. Extracted
/// so the quality gate, live-tag resolution, and section assembly are testable
/// without the singleton store.
enum ContextWorkstreamPooling {
  /// Facts below this worthiness never earn pooled quota; measured against the
  /// live fact corpus, a recency-only pool surfaces scaffolding and w=0 noise.
  static let worthinessFloor = 0.3
  static let maximumItems = 8
  /// Diversity cap so one chatty sibling bucket cannot fill the section.
  static let maximumPerBucket = 3
  static let recencyHalfLifeHours = 6.0
  /// Bound on candidates fetched from SQL before in-memory scoring.
  static let candidateFetchLimit = 200
  /// Cross-app facts too new for the reconciler to have tagged: last 15 minutes,
  /// high-worthiness only, one per source bucket, three total.
  static let recentContextWindow: TimeInterval = 15 * 60
  static let recentContextWorthinessFloor = 0.6
  static let recentContextMaximumItems = 3
  static let recentContextMaximumPerBucket = 1
  /// A bucket majority tag only stands in for a missing own-visit tag when it
  /// is this dominant among the bucket's tagged facts…
  static let bucketMajorityShare = 0.8
  /// …and the bucket has at least this many tagged facts to have a majority of.
  static let bucketMajorityMinimumFacts = 3

  private static let scaffoldingPrefixes = [
    "identifier", "ambient narrative", "evidence fragment", "evidence record",
    "proposed record", "proposed fact", "proposal ", "proposal:",
  ]

  /// Extraction-model scaffolding re-copied into `statement` reads as prose but
  /// carries no information worth cross-bucket quota.
  static func isScaffolding(_ statement: String) -> Bool {
    let lowered = statement.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return scaffoldingPrefixes.contains { lowered.hasPrefix($0) }
  }

  /// The workstream the director should pool for right now. The visit's own
  /// freshly extracted facts are the strongest signal; a bucket-majority tag
  /// stands in only when it is overwhelming, so genuinely multi-topic surfaces
  /// (a chat app hosting several projects) stay bucket-only rather than pooling
  /// the wrong project's context.
  static func liveTag(
    ownTagCounts: [String: Int], bucketTagCounts: [String: Int]
  ) -> String? {
    if let own = ownTagCounts.max(by: { ($0.value, $1.key) < ($1.value, $0.key) }), own.value > 0 {
      return own.key
    }
    let total = bucketTagCounts.values.reduce(0, +)
    guard total >= bucketMajorityMinimumFacts else { return nil }
    guard let dominant = bucketTagCounts.max(by: { ($0.value, $1.key) < ($1.value, $0.key) })
    else { return nil }
    guard Double(dominant.value) >= bucketMajorityShare * Double(total) else { return nil }
    return dominant.key
  }

  /// Quality gate and ranking: worthiness floor, scaffolding filter, then
  /// worthiness plus a recency half-life, capped per source bucket.
  static func select(
    _ candidates: [ContextWorkstreamPoolItem],
    now: Date,
    worthinessFloor: Double = Self.worthinessFloor,
    maximumItems: Int = Self.maximumItems,
    maximumPerBucket: Int = Self.maximumPerBucket,
    createdAfter: Date? = nil
  ) -> [ContextWorkstreamPoolItem] {
    let scored =
      candidates
      .filter { item in
        item.notifyWorthiness >= worthinessFloor && !isScaffolding(item.statement)
          && (createdAfter.map { item.createdAt >= $0 } ?? true)
      }
      .map { item -> (score: Double, item: ContextWorkstreamPoolItem) in
        let ageHours = max(0, now.timeIntervalSince(item.createdAt)) / 3600
        return (item.notifyWorthiness + pow(0.5, ageHours / recencyHalfLifeHours), item)
      }
      .sorted { lhs, rhs in
        if lhs.score != rhs.score { return lhs.score > rhs.score }
        return lhs.item.factID < rhs.item.factID
      }
    var perBucket: [String: Int] = [:]
    var selected: [ContextWorkstreamPoolItem] = []
    for (_, item) in scored {
      guard perBucket[item.bucketID, default: 0] < maximumPerBucket else { continue }
      perBucket[item.bucketID, default: 0] += 1
      selected.append(item)
      if selected.count == maximumItems { break }
    }
    return selected
  }

  /// Newest high-worthiness facts from other windows, too fresh for tagging.
  static func selectRecent(
    _ candidates: [ContextWorkstreamPoolItem], now: Date
  ) -> [ContextWorkstreamPoolItem] {
    select(
      candidates,
      now: now,
      worthinessFloor: recentContextWorthinessFloor,
      maximumItems: recentContextMaximumItems,
      maximumPerBucket: recentContextMaximumPerBucket,
      createdAfter: now.addingTimeInterval(-recentContextWindow))
  }

  /// The section rides in the uncached volatile suffix, below the untrusted
  /// preamble that opens the stable prompt, exactly like the retrieval hop's
  /// section. Pooled facts are printed without their ids on purpose: the
  /// director cannot cite what it was never handed a ref for, so delivery
  /// grounding remains own-bucket by construction.
  static func promptSection(tag: String, items: [ContextWorkstreamPoolItem], now: Date) -> String? {
    formattedSection(
      header: "RELATED WORKSTREAM CONTEXT (\(tag))",
      intro: """
        Validated facts from other buckets in the same workstream, most relevant first.
        Context only: use them to connect what the user is doing across apps.
        They are not citable: never place them in bucket_entry_refs or fact_ids.
        Do not re-deliver a point they already cover from this bucket.
        """,
      items: items,
      now: now)
  }

  static func recentContextPromptSection(
    items: [ContextWorkstreamPoolItem], now: Date
  ) -> String? {
    formattedSection(
      header: "RECENT CONTEXT FROM OTHER WINDOWS (last 15 min)",
      intro: """
        Validated facts from other windows in the last 15 minutes, most relevant first.
        Context only: use them to connect what the user is doing across apps.
        They are not citable: never place them in bucket_entry_refs or fact_ids.
        Do not re-deliver a point they already cover from this bucket.
        """,
      items: items,
      now: now)
  }

  private static func formattedSection(
    header: String,
    intro: String,
    items: [ContextWorkstreamPoolItem],
    now: Date
  ) -> String? {
    guard !items.isEmpty else { return nil }
    let lines = items.map { item in
      "- [\(String(item.appName.prefix(24))), \(relativeAge(from: item.createdAt, now: now))] "
        + String(item.statement.prefix(300))
    }
    return """
      == \(header) ==
      \(intro)
      \(lines.joined(separator: "\n"))
      """
  }

  static func relativeAge(from createdAt: Date, now: Date) -> String {
    let seconds = max(0, Int(now.timeIntervalSince(createdAt).rounded(.down)))
    if seconds < 60 { return "\(seconds)s ago" }
    let minutes = seconds / 60
    if minutes < 60 { return "\(minutes)m ago" }
    let hours = minutes / 60
    if hours < 48 { return "\(hours)h ago" }
    return "\(hours / 24)d ago"
  }
}
