import Foundation
import GRDB

/// Derives a shared *destination* identity for browser contexts.
///
/// Bucket identity is otherwise `sha256(app::normalized window title)`, so every
/// distinct tab title becomes its own bucket. That is correct for native apps —
/// one Telegram thread per title is exactly right — but wrong for browsers, where
/// one destination produces many titles (`Home / X`, `Notifications / X`, an
/// individual post) and none of them accumulate.
///
/// This type turns a browser title into a durable key such as `x.com/feed` or
/// `github.com/acme/repo`, which several reference hashes can then share.
///
/// Scope is deliberately limited to browsers. Unscoped destination labelling was
/// measured at 6% precision because the model answers `telegram` for every thread
/// and collapses unrelated private conversations into one bucket. Native-app title
/// identity is already correct and is left completely untouched.
enum ContextDestinationKey {
  /// Prefix stored in `context_buckets.subjectID` / `subject_bindings.subjectID`.
  static let subjectPrefix = "dest:"
  /// Recorded in `subject_bindings.source`. The generation suffix lets a whole
  /// cohort be purged and lazily re-derived after a prompt or model change.
  static let derivationSource = "derived_destination:v1"

  private static let browserTokens = [
    "chrome", "safari", "firefox", "arc", "edge", "brave", "vivaldi", "opera",
  ]
  /// Domains the model must never emit: naming the browser would merge every tab.
  private static let forbiddenDomains: Set<String> = [
    "chrome", "google-chrome", "googlechrome", "browser", "safari", "firefox", "arc", "edge",
    "brave", "vivaldi", "opera", "unknown", "localhost",
  ]
  /// Too generic to evidence a domain claim against a title.
  private static let genericDomainParts: Set<String> = [
    "com", "org", "io", "net", "co", "www", "app", "apps", "google", "web", "html",
  ]

  static func isBrowser(appName: String) -> Bool {
    let lowered = appName.lowercased()
    return browserTokens.contains { lowered.contains($0) }
  }

  /// The trailing site token of a window title (`… · acme/repo` → `acme/repo`).
  ///
  /// Supplying this measurably outperformed supplying more prose context: it moved
  /// precision by +15 points where extra accumulated facts moved it by +2. Browser
  /// titles are truncated mid-string with an ellipsis, so the *trailing* segment is
  /// the part that reliably survives.
  static func siteHint(title: String) -> String? {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    for separator in ["·", "—", "–", " - ", "|"] {
      if let range = trimmed.range(of: separator, options: .backwards) {
        let tail = trimmed[range.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)
        if tail.count >= 2, tail.count <= 40 { return tail.lowercased() }
      }
    }
    return nil
  }

  /// Validates a model-proposed key and returns the storable subject ID.
  ///
  /// Returns nil whenever the key cannot be trusted, which leaves the context on
  /// its existing per-title identity. Failing to nil is always the safe direction:
  /// under-merging costs an extra bucket, over-merging pollutes an accumulated
  /// fact set that the director later cites in notifications.
  static func sanitize(_ proposed: String?, title: String) -> String? {
    guard var key = proposed?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
      !key.isEmpty
    else { return nil }

    key = key.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
    while key.hasSuffix("/") { key.removeLast() }
    guard key.count >= 3, key.count <= 120 else { return nil }
    // The model is told to answer `unknown/<title>` when it cannot identify the
    // site. That is an abstention, not a key.
    guard !key.hasPrefix("unknown") else { return nil }

    let domain = key.split(separator: "/", maxSplits: 1).first.map(String.init) ?? key
    guard !domain.isEmpty, !forbiddenDomains.contains(domain) else { return nil }
    guard isGrounded(key: key, domain: domain, title: title) else { return nil }
    return subjectPrefix + key
  }

  /// Requires the claimed domain to be evidenced by the title itself.
  ///
  /// A free, deterministic check against hallucinated destinations — it rejects a
  /// title reading `re: modulate transcription - …ever.com` being labelled
  /// `scalingforever.com/inbox`. Measured effect: precision 85% → 89% with no loss
  /// of recall, because every key it rejected belonged to a single-visit context.
  private static func isGrounded(key: String, domain: String, title: String) -> Bool {
    let haystack = title.lowercased()
    // No minimum length here on purpose. `x.com` reduces to just "x" once the
    // generic TLD is dropped, and X was ten of the fragmented buckets — a length
    // floor silently made the single most fragmented site ineligible to merge.
    // This matches the implementation the 89%-precision measurement was taken on.
    let domainParts = domain.split(whereSeparator: { $0 == "." || $0 == "-" })
      .map(String.init)
      .filter { !genericDomainParts.contains($0) }
    if domainParts.contains(where: { haystack.contains($0) }) { return true }

    let section = key.split(separator: "/", maxSplits: 1).dropFirst().joined(separator: "/")
    let sectionParts = section.split(whereSeparator: { "/-_ ".contains($0) })
      .map(String.init)
      .filter { $0.count > 3 }
    return sectionParts.contains(where: { haystack.contains($0) })
  }

  /// Appended to the existing extraction prompt for browser contexts only.
  ///
  /// This rides the extraction call rather than opening a lane of its own: the
  /// backend's `ProactiveOperation` enum is closed, so a new operation would need
  /// a provisioned gateway lane and its own quota. Extraction already runs at the
  /// moment a bucket exists and content is known, which is exactly when the
  /// destination can be decided.
  static func promptFragment(title: String) -> String {
    var fragment = """
      Also identify which website page-group this tab belongs to, as "destination".

      Answer a key "<domain>/<section>", lowercase. Examples:
        x.com/feed   github.com/acme/repo   mail.google.com/inbox   app.codemagic.io/builds

      Rules, in order of importance:
      1. Never answer with the browser's name. "chrome", "safari", "browser" are forbidden.
      2. Infer the domain from the title's site suffix or wording. Titles are truncated
         with "…", so the trailing part after the last separator is usually the site.
      3. <section> is the durable area of that site — feed, inbox, builds, the repository
         path — never the individual post, message, issue or document currently open.
      4. Different websites, repositories, mailboxes and chat workspaces are ALWAYS
         different keys.
      5. If you cannot confidently identify the website, answer exactly
         "unknown/\(title)". Never guess a domain you are unsure of.
      """
    if let hint = siteHint(title: title) {
      fragment += "\n\nTrailing site token: \(hint)"
    }
    return fragment
  }

  /// Non-browser contexts still receive the field because OpenAI strict structured
  /// output requires every declared property to be present; they are told to
  /// abstain, and `isBrowser` gates the result client-side regardless.
  static let abstention = "unknown/"
}

/// Writes a derived destination binding. Split out as a static function over a
/// `Database` so the identity rules are unit-testable without the actor or the
/// live pool, matching `ContextBucketVisitResolver`.
enum ContextDestinationBinder {
  /// Returns the bucket the destination resolved to, or nil when nothing changed.
  @discardableResult
  static func apply(
    in db: Database,
    referenceHash: String,
    currentBucketID: String,
    subjectID: String,
    now: Date = Date()
  ) throws -> String? {
    guard subjectID.hasPrefix(ContextDestinationKey.subjectPrefix) else { return nil }
    // Ephemeral hashes exist precisely so blank/noise titles never share identity.
    guard !referenceHash.hasPrefix("ephemeral:") else { return nil }

    let binding = try Row.fetchOne(
      db, sql: "SELECT * FROM subject_bindings WHERE referenceHash = ?",
      arguments: [referenceHash])
    guard let binding else { return nil }
    // Explicit user or automation intent always outranks a derived key, and a
    // destination already applied needs no second decision.
    let source: String = binding["source"] ?? ""
    guard source != "explicit_open", !source.hasPrefix("derived_destination:") else { return nil }
    let currentSubjectID: String? = binding["subjectID"]
    guard currentSubjectID != subjectID else { return nil }

    let existing = try String.fetchOne(
      db,
      sql: """
        SELECT id FROM context_buckets
        WHERE subjectKind = 'context' AND subjectID = ? AND workstreamID IS NULL
        LIMIT 1
        """,
      arguments: [subjectID])

    let resolved: String
    if let existing {
      // Another title already owns this destination: point future visits there.
      // Entries already written stay put — re-parenting historical facts is the
      // one operation that could retroactively poison an accumulated bucket.
      resolved = existing
    } else {
      // Claim the destination for this bucket. Safe against the
      // UNIQUE(subjectKind, subjectID, workstreamID) index because the SELECT
      // above ran inside this same write transaction.
      try db.execute(
        sql: """
          UPDATE context_buckets
          SET subjectID = ?, displayLabel = COALESCE(displayLabel, ?), updatedAt = ?
          WHERE id = ? AND subjectKind = 'context' AND workstreamID IS NULL
          """,
        arguments: [subjectID, subjectID, now, currentBucketID])
      guard db.changesCount > 0 else { return nil }
      resolved = currentBucketID
    }

    try db.execute(
      sql: """
        UPDATE subject_bindings
        SET bucketID = ?, subjectKind = 'context', subjectID = ?, source = ?, updatedAt = ?
        WHERE referenceHash = ?
        """,
      arguments: [
        resolved, subjectID, ContextDestinationKey.derivationSource, now, referenceHash,
      ])
    return resolved
  }
}
