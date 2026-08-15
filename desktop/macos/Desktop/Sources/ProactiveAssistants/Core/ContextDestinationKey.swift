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

  /// Exact application names. Substring matching was wrong here: "Ledger Live"
  /// contains "edge" and "Archive Utility" contains "arc", which would hand native
  /// apps a browser-only code path.
  private static let browserAppNames: Set<String> = [
    "google chrome", "google chrome canary", "google chrome beta", "chromium", "safari",
    "safari technology preview", "firefox", "firefox developer edition", "arc",
    "microsoft edge", "brave browser", "vivaldi", "opera", "opera gx", "orion", "zen browser",
  ]
  /// First domain labels the model must never emit: naming the browser would merge
  /// every open tab into one bucket.
  private static let forbiddenDomainLabels: Set<String> = [
    "chrome", "chromium", "browser", "safari", "firefox", "arc", "edge", "brave", "vivaldi",
    "opera", "orion", "unknown", "localhost", "newtab", "about", "file",
  ]
  /// Web messengers. A browser tab on one of these carries a single conversation in
  /// its title, exactly like the native clients, so destination grouping would merge
  /// distinct private threads — the worst outcome measured (6% precision) and the
  /// reason routing is browser-scoped at all. Excluding them keeps that guarantee
  /// from being reachable through the browser path.
  private static let messengerHosts: Set<String> = [
    "slack", "discord", "telegram", "whatsapp", "messenger", "teams", "signal", "matrix",
    "element", "chat", "imessage", "zulip", "mattermost",
  ]
  /// Too generic to evidence a domain claim against a title.
  private static let genericDomainParts: Set<String> = [
    "com", "org", "io", "net", "co", "www", "app", "apps", "google", "web", "html",
  ]
  /// Section words that name a generic area of *any* site. These cannot be the sole
  /// evidence for a domain claim: otherwise `x.com/feed` grounds against any title
  /// containing "feed", and every site with a feed collapses into the X bucket.
  private static let genericSectionWords: Set<String> = [
    "feed", "inbox", "home", "mail", "builds", "build", "search", "news", "chat",
    "threads", "posts", "notifications", "dashboard", "settings", "profile", "explore",
    "timeline", "messages", "main", "index", "overview", "start",
  ]

  static func isBrowser(appName: String) -> Bool {
    browserAppNames.contains(appName.lowercased().trimmingCharacters(in: .whitespaces))
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

    let split = key.split(separator: "/", maxSplits: 1).map(String.init)
    let domain = split.first ?? key
    // A bare domain is too coarse an identity: `github.com` with no section would
    // collapse every repository into one bucket. The prompt always asks for
    // `<domain>/<section>`, so enforce that contract.
    let section = split.count > 1 ? split[1] : ""
    guard !domain.isEmpty, !section.trimmingCharacters(in: .whitespaces).isEmpty else {
      return nil
    }
    // Every label, not just the first: `google-chrome/tabs` names the browser in its
    // second label, and `chrome.com/tabs` does so just as effectively as `chrome/tabs`.
    let labels = domain.split(whereSeparator: { $0 == "." || $0 == "-" }).map(String.init)
    guard !labels.isEmpty, !labels.contains(where: { forbiddenDomainLabels.contains($0) }) else {
      return nil
    }
    guard !labels.contains(where: { messengerHosts.contains($0) }) else { return nil }
    // A web messenger reached through the browser must also stay per-title even when
    // the model names a different domain, because the *title* is the conversation.
    guard !titleLooksLikeMessenger(title) else { return nil }
    guard isGrounded(key: key, domain: domain, title: title) else { return nil }
    return subjectPrefix + key
  }

  private static func titleLooksLikeMessenger(_ title: String) -> Bool {
    let tokens = tokenize(title)
    return tokens.contains(where: { messengerHosts.contains($0) })
  }

  /// Word tokens of a title, lowercased.
  private static func tokenize(_ value: String) -> Set<String> {
    Set(
      value.lowercased()
        .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
        .map(String.init))
  }

  /// Requires the claimed domain to be evidenced by the title itself.
  ///
  /// A free, deterministic check against hallucinated destinations — it rejects a
  /// title reading `re: modulate transcription - …ever.com` being labelled
  /// `scalingforever.com/inbox`. Measured effect: precision 85% → 89% with no loss
  /// of recall, because every key it rejected belonged to a single-visit context.
  private static func isGrounded(key: String, domain: String, title: String) -> Bool {
    let haystack = title.lowercased()
    let tokens = tokenize(title)
    let domainParts = domain.split(whereSeparator: { $0 == "." || $0 == "-" })
      .map(String.init)
      .filter { !genericDomainParts.contains($0) }
    // A domain of nothing but generic parts carries no identity: `com/feed` would
    // otherwise become one shared key for every site with "feed" in its title.
    guard !domainParts.isEmpty else { return false }

    // Short labels must match a *whole* title token; only longer ones may match a
    // substring. A plain substring test with no length floor let `x.com` ground
    // against any title containing the letter x — "fix: thing #11 · acme/omi"
    // grounded `x.com/feed`, permanently parking a GitHub tab in the X bucket.
    // A length floor alone was also wrong: it dropped `x.com` entirely and made X,
    // the single most fragmented site, ineligible to merge.
    if domainParts.contains(where: { part in
      part.count >= 4 ? haystack.contains(part) : tokens.contains(part)
    }) {
      return true
    }

    // Section evidence is kept, because browser titles are truncated from the left:
    // `fix: thing #11 · acme/omi` never contains "github", and dropping this
    // fallback measurably regressed exactly the repository grouping this feature
    // exists to provide. But a *generic* section word cannot stand in for domain
    // evidence, or `x.com/feed` grounds on any page that mentions a feed.
    let section = key.split(separator: "/", maxSplits: 1).dropFirst().joined(separator: "/")
    let sectionParts = section.split(whereSeparator: { "/-_ ".contains($0) })
      .map(String.init)
      .filter { $0.count > 3 && !genericSectionWords.contains($0) }
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
      5. If you cannot confidently identify the website, answer exactly "unknown/".
         Never guess a domain you are unsure of.
      """
    // The title reaches the model through the `Window:` line above, which sits under
    // `untrustedPreamble`. It must not be interpolated into the rules themselves:
    // a page controls its own title, and a newline inside one would let it append
    // instructions that read as rule text rather than as quoted data.
    if let hint = siteHint(title: title) {
      fragment += "\n\nTrailing site token: \(singleLine(hint))"
    }
    return fragment
  }

  /// Collapses newlines and control characters so untrusted text cannot forge
  /// prompt structure, and clamps length.
  static func singleLine(_ value: String, limit: Int = 60) -> String {
    let flattened = value.unicodeScalars
      .map { CharacterSet.newlines.contains($0) || CharacterSet.controlCharacters.contains($0) ? " " : Character($0) }
      .reduce(into: "") { $0.append($1) }
    let collapsed = flattened.replacingOccurrences(
      of: #"\s+"#, with: " ", options: .regularExpression)
    return String(collapsed.trimmingCharacters(in: .whitespaces).prefix(limit))
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
    // Both explicit sources: the one-time UserDefaults import records a user's own
    // prior binding as `legacy_explicit_open`, and a derived key must not overwrite
    // that any more than it may overwrite a fresh `explicit_open`.
    guard !source.hasSuffix("explicit_open"), !source.hasPrefix("derived_destination:") else {
      return nil
    }
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
      //
      // Freshness must still move. `finalizeVisit` credits the visit to the
      // per-title bucket, and `context_visits.bucketID` keeps pointing there, so
      // without this the destination looks untouched: stale GC (30-day
      // `lastVisitedAt`) and overflow GC (keep newest 250) would both prefer
      // deleting the destination over the orphans feeding it. That is worst for
      // exactly the visit-once-and-never-return titles this feature exists to join.
      try db.execute(
        sql: """
          UPDATE context_buckets
          SET visitCount = visitCount + 1, lastVisitedAt = ?, updatedAt = ?
          WHERE id = ?
          """,
        arguments: [now, now, existing])
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
