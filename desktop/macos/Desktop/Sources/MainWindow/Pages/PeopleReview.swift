import Foundation

// MARK: - Human-in-the-loop review + user overrides
//
// Backs the People tab's "review / confirm / correct" surface. The on-device engine
// (`PeopleGraphBuilder`) flags low-confidence identities/facts and writes a `reviewQueue`
// into `people_intelligence.json`; the user's answers are persisted here to
// `~/Library/Application Support/Omi/users/<uid>/people_overrides.json` and re-read by the
// engine on every run so **user truth always wins over inference**. Everything stays on-device.

/// A single low-confidence item the user is asked to confirm/correct. Decoded from the engine's
/// `reviewQueue`. Extra id/pair/fact fields carry the context needed to persist the decision.
struct PeopleReviewItem: Decodable, Identifiable, Equatable, Sendable {
  let id: String
  let name: String
  /// "identity" (are these two the same person?) or "fact" (is this asserted fact correct?).
  let kind: String
  let question: String
  let options: [String]?
  /// Identity items: the two canonical person ids being compared.
  let a: String?
  let b: String?
  /// Fact items: the person and the exact inferred fact text under review.
  let personId: String?
  let fact: String?

  var isIdentity: Bool { kind == "identity" }

  enum CodingKeys: String, CodingKey {
    case id, name, kind, question, options, a, b, personId, fact
  }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    id = (try c.decodeIfPresent(String.self, forKey: .id)) ?? UUID().uuidString
    name = (try c.decodeIfPresent(String.self, forKey: .name)) ?? ""
    kind = (try c.decodeIfPresent(String.self, forKey: .kind)) ?? "identity"
    question = (try c.decodeIfPresent(String.self, forKey: .question)) ?? ""
    options = try c.decodeIfPresent([String].self, forKey: .options)
    a = try c.decodeIfPresent(String.self, forKey: .a)
    b = try c.decodeIfPresent(String.self, forKey: .b)
    personId = try c.decodeIfPresent(String.self, forKey: .personId)
    fact = try c.decodeIfPresent(String.self, forKey: .fact)
  }
}

/// The user's saved corrections, persisted to `people_overrides.json`. Read by `PeopleGraphBuilder`
/// on every run and applied so confirmed merges/splits, corrected facts, and dismissed items are
/// respected. All arrays are tolerant of a missing/partial file (fresh user → empty).
struct PeopleOverrides: Codable, Equatable {
  struct IdentityDecision: Codable, Equatable {
    var a: String
    var b: String
    /// true → the two are the same person (merge); false → confirmed different (keep separate).
    var same: Bool
  }

  struct FactEdit: Codable, Equatable {
    var id: String
    var original: String
    /// The corrected text; an empty string means "drop this fact".
    var corrected: String
  }

  var identity: [IdentityDecision]
  var factEdits: [FactEdit]
  /// Review-item ids the user skipped/handled — never surfaced again.
  var dismissed: [String]

  init(
    identity: [IdentityDecision] = [], factEdits: [FactEdit] = [], dismissed: [String] = []
  ) {
    self.identity = identity
    self.factEdits = factEdits
    self.dismissed = dismissed
  }

  enum CodingKeys: String, CodingKey { case identity, factEdits, dismissed }

  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    identity = (try? c.decode([IdentityDecision].self, forKey: .identity)) ?? []
    factEdits = (try? c.decode([FactEdit].self, forKey: .factEdits)) ?? []
    dismissed = (try? c.decode([String].self, forKey: .dismissed)) ?? []
  }
}

/// Resolves the per-user directory that holds `people_intelligence.json` / `people_overrides.json`.
/// Prefers the signed-in uid; otherwise scans `Omi/users/*/` for the one dir that has the people
/// file — the same resolution `PeopleViewModel` / `PeopleGraphBuilder` use, so all three agree.
enum PeopleUserDirectory {
  static func resolve(uid: String?) -> URL? {
    let fm = FileManager.default
    guard let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
    else { return nil }
    let usersDir = support.appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)

    if let uid, !uid.isEmpty {
      let dir = usersDir.appendingPathComponent(uid, isDirectory: true)
      // Prefer the dir that already has the people file, but accept an existing uid dir so a
      // correction can be saved even before the file is first written.
      if fm.fileExists(atPath: dir.appendingPathComponent("people_intelligence.json").path) {
        return dir
      }
      if fm.fileExists(atPath: dir.path) { return dir }
    }
    guard
      let entries = try? fm.contentsOfDirectory(
        at: usersDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
    else { return nil }
    for entry in entries
    where fm.fileExists(atPath: entry.appendingPathComponent("people_intelligence.json").path) {
      return entry
    }
    return nil
  }
}

/// Reads/writes `people_overrides.json`. All IO is guarded — a correction that fails to persist
/// must never crash the app; it is simply retried on the next decision.
enum PeopleOverridesStore {
  static let fileName = "people_overrides.json"

  static func load(directory: URL) -> PeopleOverrides {
    let url = directory.appendingPathComponent(fileName)
    guard let data = try? Data(contentsOf: url),
      let overrides = try? JSONDecoder().decode(PeopleOverrides.self, from: data)
    else { return PeopleOverrides() }
    return overrides
  }

  static func load(uid: String?) -> PeopleOverrides {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return PeopleOverrides() }
    return load(directory: dir)
  }

  static func save(_ overrides: PeopleOverrides, directory: URL) {
    let url = directory.appendingPathComponent(fileName)
    do {
      let encoder = JSONEncoder()
      encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
      let data = try encoder.encode(overrides)
      try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
      try data.write(to: url, options: .atomic)
    } catch {
      // Best-effort persistence; a write failure is non-fatal and self-heals on the next decision.
    }
  }

  /// Read-modify-write helper. Returns false only when no user directory could be resolved.
  @discardableResult
  static func mutate(uid: String?, _ change: (inout PeopleOverrides) -> Void) -> Bool {
    guard let dir = PeopleUserDirectory.resolve(uid: uid) else { return false }
    var overrides = load(directory: dir)
    change(&overrides)
    save(overrides, directory: dir)
    return true
  }

  static func recordIdentity(a: String, b: String, same: Bool, uid: String?) {
    mutate(uid: uid) { overrides in
      overrides.identity.removeAll { ($0.a == a && $0.b == b) || ($0.a == b && $0.b == a) }
      overrides.identity.append(.init(a: a, b: b, same: same))
    }
  }

  static func recordFactEdit(id: String, original: String, corrected: String, uid: String?) {
    mutate(uid: uid) { overrides in
      overrides.factEdits.removeAll { $0.id == id && $0.original == original }
      overrides.factEdits.append(.init(id: id, original: original, corrected: corrected))
    }
  }

  static func dismiss(id: String, uid: String?) {
    mutate(uid: uid) { overrides in
      if !overrides.dismissed.contains(id) { overrides.dismissed.append(id) }
    }
  }
}

// MARK: - Correct-by-chat

/// Routes a "Fix in chat" / "Looks wrong?" action to the app's existing chat surface, prefilling
/// the Home ask bar so the user reviews and edits before sending. Reuses the shared chat provider
/// (`ChatProvider.mainInstance`, the same instance the Home ask bar binds to) and the existing
/// `.navigateToChat` navigation — no new chat engine.
enum PeopleChatCorrection {
  @MainActor
  static func fixInChat(name: String) {
    let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
    let subject = trimmed.isEmpty ? "this person" : trimmed
    ChatProvider.mainInstance?.draftText = "Correct what you know about \(subject). Here's what's off: "
    NotificationCenter.default.post(name: .navigateToChat, object: nil)
  }

  /// Sends a person-scoped question to chat. The profile page's ask bar and its
  /// suggested prompts both route here so there is one chat hand-off, not two.
  @MainActor
  static func ask(prompt: String) {
    let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    ChatProvider.mainInstance?.draftText = trimmed
    NotificationCenter.default.post(name: .navigateToChat, object: nil)
  }
}
