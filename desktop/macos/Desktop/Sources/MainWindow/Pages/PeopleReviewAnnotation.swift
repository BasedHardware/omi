import Foundation

// MARK: - Human-in-the-loop review + user overrides
//
// The engine asserts identities and facts it inferred, and inference is sometimes wrong. This is
// the surface that keeps it honest: weak-signal people are flagged rather than stated, the
// questions worth asking are surfaced as a capped review queue, and the user's saved answers are
// folded back over the derived data so their truth always wins.
//
// Split out of `PeopleGraphBuilder.swift` because it is a self-contained concern — pure, no IO, and
// exercised end-to-end by `PeopleOverridesApplyTests` — and the graph builder is at its line
// budget. Everything here is a verbatim move; behavior is unchanged.

extension PeopleGraphBuilder {

  /// Cap on low-confidence items surfaced at once, keeping the "Needs your confirmation" surface
  /// glanceable rather than an endless backlog.
  static let reviewQueueCap = 20
  /// Only the closest N people (the array is pre-sorted by closeness) are scanned for similar-name
  /// identity collisions, bounding the O(n²) pair scan on large lists.
  private static let similarNameScanLimit = 160

  /// Annotate weak-signal people with `needsConfirmation` / `confirmReason`, derive a capped
  /// `reviewQueue` of low-confidence items, then fold the user's saved decisions in so user truth
  /// always wins. Pure (no IO) and idempotent — safe to run on every write.
  ///
  /// Weak signals flagged today:
  ///   - a name that is edit-distance-close to another canonical person (e.g. Prisha / Pritha) —
  ///     surfaced as an `identity` question the user confirms, splits, or skips;
  ///   - a first-name-only identity that collides with another person's first name (ambiguous
  ///     "which one?") — surfaced as the same `identity` question;
  ///   - a `fact` carried by an identity-uncertain person — surfaced as a `fact` question the user
  ///     accepts, rejects (drops), or edits.
  static func annotateAndReview(
    persons: [[String: Any]], overrides: PeopleOverrides
  ) -> (people: [[String: Any]], reviewQueue: [[String: Any]]) {
    var people = persons
    var review: [[String: Any]] = []

    func id(_ p: [String: Any]) -> String { (p["id"] as? String) ?? "" }
    func name(_ p: [String: Any]) -> String { (p["name"] as? String) ?? "" }
    func pairKey(_ a: String, _ b: String) -> String { a < b ? "\(a)|\(b)" : "\(b)|\(a)" }

    // ---- 1. similar-name identity collisions (the Prisha / Pritha case) ----
    let scanCount = min(people.count, similarNameScanLimit)
    var flaggedPairs = Set<String>()
    if scanCount >= 2 {
      outer: for i in 0..<(scanCount - 1) {
        for j in (i + 1)..<scanCount {
          let na = norm(name(people[i]))
          let nb = norm(name(people[j]))
          guard !na.isEmpty, !nb.isEmpty, na != nb, na.first == nb.first else { continue }
          guard min(na.count, nb.count) >= 4 else { continue }
          let dist = editDistance(na, nb)
          guard dist >= 1, dist <= 2 else { continue }
          let a = id(people[i])
          let b = id(people[j])
          guard !a.isEmpty, !b.isEmpty, a != b else { continue }
          let key = pairKey(a, b)
          guard !flaggedPairs.contains(key) else { continue }
          flaggedPairs.insert(key)
          people[i]["needsConfirmation"] = true
          people[i]["confirmReason"] = "Name is very close to \(name(people[j])) — might be the same person"
          people[j]["needsConfirmation"] = true
          people[j]["confirmReason"] = "Name is very close to \(name(people[i])) — might be the same person"
          review.append([
            "id": "identity:\(key)",
            "name": name(people[i]),
            "kind": "identity",
            "question": "Are \(name(people[i])) and \(name(people[j])) the same person?",
            "options": ["Confirm", "Not the same", "Skip"],
            "a": a,
            "b": b,
          ])
          if review.count >= reviewQueueCap { break outer }
        }
      }
    }

    // ---- 2. first-name-only collisions (two identities that are just the same first name) ----
    // A single-token name is a weak identity; when two distinct people share the exact same one
    // (e.g. two "Alex" cards), ask which — rather than assuming they are the same or different.
    if review.count < reviewQueueCap {
      var byFirstNameOnly: [String: [Int]] = [:]
      for idx in 0..<min(people.count, similarNameScanLimit) {
        let n = norm(name(people[idx]))
        guard !n.isEmpty, !n.contains(" "), n.count >= 2 else { continue }  // single token only
        byFirstNameOnly[n, default: []].append(idx)
      }
      for firstName in byFirstNameOnly.keys.sorted() {
        guard review.count < reviewQueueCap, let indices = byFirstNameOnly[firstName], indices.count >= 2
        else { continue }
        // One question per colliding first name: pair the two closest (indices are closeness-sorted).
        let i = indices[0]
        let j = indices[1]
        let a = id(people[i])
        let b = id(people[j])
        guard !a.isEmpty, !b.isEmpty, a != b else { continue }
        let key = pairKey(a, b)
        guard !flaggedPairs.contains(key) else { continue }
        flaggedPairs.insert(key)
        for idx in indices {
          people[idx]["needsConfirmation"] = true
          people[idx]["confirmReason"] = "Matched on a first name only — may be more than one person"
        }
        review.append([
          "id": "identity:\(key)",
          "name": name(people[i]),
          "kind": "identity",
          "question": "You have two contacts named \(name(people[i])) — are they the same person?",
          "options": ["Confirm", "Not the same", "Skip"],
          "a": a,
          "b": b,
        ])
      }
    }

    // ---- 3. fact confirmation for identity-uncertain people that carry inferred facts ----
    if review.count < reviewQueueCap {
      for idx in people.indices {
        guard review.count < reviewQueueCap else { break }
        guard (people[idx]["needsConfirmation"] as? Bool) == true else { continue }
        guard let facts = people[idx]["facts"] as? [String],
          let fact = facts.first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })
        else { continue }
        let pid = id(people[idx])
        review.append([
          "id": "fact:\(pid)",
          "name": name(people[idx]),
          "kind": "fact",
          "question": "Is this right about \(name(people[idx]))? \u{201C}\(fact)\u{201D}",
          "options": ["Yes", "No", "Edit"],
          "personId": pid,
          "fact": fact,
        ])
      }
    }

    return applyOverrides(people: people, reviewQueue: review, overrides: overrides)
  }

  /// Fold the user's saved decisions onto derived people + review items. **User truth wins:**
  /// a confirmed-same identity merges the two cards, a confirmed-different / skipped / edited item
  /// never resurfaces, and a corrected fact replaces (or, when blank, drops) the inferred text.
  /// Pure and deterministic — no IO.
  static func applyOverrides(
    people: [[String: Any]], reviewQueue: [[String: Any]], overrides: PeopleOverrides
  ) -> (people: [[String: Any]], reviewQueue: [[String: Any]]) {
    var byIndex = people
    func indexOf(_ pid: String) -> Int? { byIndex.firstIndex { ($0["id"] as? String) == pid } }
    func pairKey(_ a: String, _ b: String) -> String { a < b ? "\(a)|\(b)" : "\(b)|\(a)" }

    var decidedPairs = Set<String>()

    // ---- identity decisions ----
    for decision in overrides.identity {
      let a = decision.a
      let b = decision.b
      guard !a.isEmpty, !b.isEmpty, a != b else { continue }
      decidedPairs.insert(pairKey(a, b))
      if decision.same {
        guard let ia = indexOf(a), let ib = indexOf(b) else {
          // One side already merged away transitively; just clear any survivor's flag.
          for pid in [a, b] { if let i = indexOf(pid) { clearConfirmation(&byIndex[i]) } }
          continue
        }
        let ca = (byIndex[ia]["closeness"] as? Double) ?? 0
        let cb = (byIndex[ib]["closeness"] as? Double) ?? 0
        let keep = ca >= cb ? ia : ib
        let drop = ca >= cb ? ib : ia
        byIndex[keep] = mergePersons(survivor: byIndex[keep], absorbed: byIndex[drop])
        clearConfirmation(&byIndex[keep])
        byIndex.remove(at: drop)
      } else {
        // Confirmed different: keep both, stop flagging/asking.
        for pid in [a, b] { if let i = indexOf(pid) { clearConfirmation(&byIndex[i]) } }
      }
    }

    // ---- fact edits (replace, or drop when the correction is blank) ----
    let unit = "\u{1F}"  // unit separator — never appears in a person id or fact
    var editedFactKeys = Set<String>()
    for edit in overrides.factEdits {
      editedFactKeys.insert("\(edit.id)\(unit)\(edit.original)")
      guard let i = indexOf(edit.id), var facts = byIndex[i]["facts"] as? [String] else { continue }
      let corrected = edit.corrected.trimmingCharacters(in: .whitespacesAndNewlines)
      if let fi = facts.firstIndex(of: edit.original) {
        if corrected.isEmpty {
          facts.remove(at: fi)
        } else {
          facts[fi] = corrected
        }
      } else if !corrected.isEmpty, !facts.contains(corrected) {
        facts.append(corrected)
      }
      byIndex[i]["facts"] = facts
    }

    // ---- filter the review queue: drop decided / edited / dismissed items ----
    let dismissed = Set(overrides.dismissed)
    let filtered = reviewQueue.filter { item in
      guard let itemId = item["id"] as? String else { return false }
      if dismissed.contains(itemId) { return false }
      let kind = item["kind"] as? String
      if kind == "identity", let a = item["a"] as? String, let b = item["b"] as? String,
        decidedPairs.contains(pairKey(a, b))
      {
        return false
      }
      if kind == "fact", let pid = item["personId"] as? String, let fact = item["fact"] as? String,
        editedFactKeys.contains("\(pid)\(unit)\(fact)")
      {
        return false
      }
      return true
    }

    return (byIndex, filtered)
  }

  private static func clearConfirmation(_ person: inout [String: Any]) {
    person["needsConfirmation"] = false
    person.removeValue(forKey: "confirmReason")
  }

  /// Merge an absorbed person into the survivor: keep the survivor's card, record the absorbed
  /// name/aliases as aliases, sum closeness, and union facts. Never loses the user-confirmed link.
  private static func mergePersons(survivor: [String: Any], absorbed: [String: Any]) -> [String: Any] {
    var out = survivor
    let survivorName = (out["name"] as? String) ?? ""
    var aliases = (out["aliases"] as? [String]) ?? []
    func addAlias(_ raw: String?) {
      guard let value = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return
      }
      if value.caseInsensitiveCompare(survivorName) == .orderedSame { return }
      if !aliases.contains(where: { $0.caseInsensitiveCompare(value) == .orderedSame }) {
        aliases.append(value)
      }
    }
    addAlias(absorbed["name"] as? String)
    for alias in (absorbed["aliases"] as? [String]) ?? [] { addAlias(alias) }
    if !aliases.isEmpty { out["aliases"] = aliases }

    let combined = ((out["closeness"] as? Double) ?? 0) + ((absorbed["closeness"] as? Double) ?? 0)
    out["closeness"] = combined

    // A user-confirmed "same person" must carry the absorbed card's identity keys across, or the
    // merge quietly makes that phone/handle unaddressable and the next run re-splits them.
    let absorbedKeys = PersonIdentityKeys.from(json: absorbed["handles"])
    if !absorbedKeys.isEmpty {
      out["handles"] = PersonIdentityKeys.from(json: out["handles"]).union(absorbedKeys).json
    }
    if (out["personUUID"] as? String)?.isEmpty ?? true, let uuid = absorbed["personUUID"] as? String,
      !uuid.isEmpty
    {
      out["personUUID"] = uuid
    }

    if let absorbedFacts = absorbed["facts"] as? [String], !absorbedFacts.isEmpty {
      var facts = (out["facts"] as? [String]) ?? []
      for fact in absorbedFacts where !facts.contains(fact) { facts.append(fact) }
      out["facts"] = facts
    }
    return out
  }

  /// Levenshtein edit distance (two-row DP). Used to detect names that are one or two edits apart
  /// (e.g. Prisha / Pritha) so a weak identity match asks instead of silently merging.
  static func editDistance(_ a: String, _ b: String) -> Int {
    let s = Array(a)
    let t = Array(b)
    if s.isEmpty { return t.count }
    if t.isEmpty { return s.count }
    var prev = Array(0...t.count)
    var curr = [Int](repeating: 0, count: t.count + 1)
    for i in 1...s.count {
      curr[0] = i
      for j in 1...t.count {
        let cost = s[i - 1] == t[j - 1] ? 0 : 1
        curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
      }
      swap(&prev, &curr)
    }
    return prev[t.count]
  }
}
