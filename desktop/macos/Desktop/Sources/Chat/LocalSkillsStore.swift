import Foundation

extension Notification.Name {
  /// Posted after the on-disk skill catalog changes (save or delete).
  static let omiUserSkillsDidChange = Notification.Name("omiUserSkillsDidChange")
}

/// User-authored skills, stored locally at `~/.omi/skills/<slug>/SKILL.md` the way
/// Claude Code uses `~/.claude/skills`. The agent reads this directory directly
/// (pi native catalog, search_skills/load_skill, and the Swift compact catalog),
/// so saving a file is all it takes for a skill to reach chat. Users can also
/// drop skill folders in by hand.
enum LocalSkillsStore {
  static let maxSkillBytes = 128 * 1024

  struct Skill: Identifiable, Equatable {
    let slug: String
    let name: String
    let description: String
    let path: String
    var id: String { slug }
  }

  /// Test seam: real code always uses the default `~/.omi`.
  nonisolated(unsafe) static var rootURLOverride: URL?

  /// `~/.omi` — also handed to pi as its agent dir, which looks for `<dir>/skills`.
  static var rootURL: URL {
    rootURLOverride
      ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".omi", isDirectory: true)
  }

  static var skillsDirURL: URL { rootURL.appendingPathComponent("skills", isDirectory: true) }

  /// The ACP lane loads `~/.omi` as a local Claude plugin only when this manifest
  /// exists — it is the gate the runtime itself applies (user-extensions.ts).
  static var pluginManifestURL: URL {
    rootURL.appendingPathComponent(".claude-plugin", isDirectory: true)
      .appendingPathComponent("plugin.json")
  }

  /// Lowercase alphanumerics joined by single hyphens, max 64 chars — the
  /// identity rule for skill folders and MCP server names alike.
  static func slugify(_ name: String) -> String {
    var out = ""
    var lastWasHyphen = true
    for scalar in name.lowercased().unicodeScalars {
      if (scalar >= "a" && scalar <= "z") || (scalar >= "0" && scalar <= "9") {
        out.unicodeScalars.append(scalar)
        lastWasHyphen = false
      } else if !lastWasHyphen {
        out.append("-")
        lastWasHyphen = true
      }
    }
    while out.hasSuffix("-") { out.removeLast() }
    return String(out.prefix(64))
  }

  static func listSkills() -> [Skill] {
    let fm = FileManager.default
    guard let dirs = try? fm.contentsOfDirectory(atPath: skillsDirURL.path) else { return [] }
    // A dot-prefixed entry is never a skill: it is a half-finished install, and listing one would
    // offer the user a skill that is about to be replaced or removed.
    return dirs.filter { !$0.hasPrefix(".") }.sorted().compactMap { slug in
      let path = skillsDirURL.appendingPathComponent(slug).appendingPathComponent("SKILL.md").path
      guard fm.fileExists(atPath: path),
        let content = try? String(contentsOfFile: path, encoding: .utf8)
      else { return nil }
      let meta = frontmatter(of: content)
      return Skill(
        slug: slug,
        name: displayName(slug: slug, frontmatterName: meta["name"]),
        description: meta["description"] ?? firstProseLine(of: content) ?? "",
        path: path)
    }
  }

  static func loadMarkdown(slug: String) -> String? {
    try? String(
      contentsOf: skillsDirURL.appendingPathComponent(slug).appendingPathComponent("SKILL.md"),
      encoding: .utf8)
  }

  /// Write a skill, normalizing the frontmatter so `name` is the slug and a
  /// description always exists (Agent Skills spec). Returns the slug.
  @discardableResult
  static func saveSkill(title: String, markdown: String, replacingSlug: String? = nil) throws -> String {
    let slug = slugify(title)
    guard !slug.isEmpty else {
      throw NSError(
        domain: "LocalSkillsStore", code: 1,
        userInfo: [NSLocalizedDescriptionKey: "Skill name must contain letters or numbers"])
    }
    let normalized = normalize(markdown: markdown, slug: slug)
    let fm = FileManager.default
    let dir = skillsDirURL.appendingPathComponent(slug, isDirectory: true)
    try fm.createDirectory(at: dir, withIntermediateDirectories: true)
    try Data(normalized.utf8).write(to: dir.appendingPathComponent("SKILL.md"), options: .atomic)
    // A rename leaves the old folder behind; remove it so the catalog has one entry.
    if let replacingSlug, replacingSlug != slug {
      try? fm.removeItem(at: skillsDirURL.appendingPathComponent(replacingSlug))
      rekeyDisabledSlug(from: replacingSlug, to: slug)
    }
    ensurePluginManifest()
    notifyChanged()
    return slug
  }

  /// Write a skill that came with bundled files, replacing any folder already at its slug.
  ///
  /// A skill folder is one unit: its `SKILL.md` references the other files by relative path, so a
  /// partial write leaves instructions pointing at nothing. Files land in a fresh folder that
  /// replaces the old one only once every byte is on disk.
  @discardableResult
  static func saveSkillBundle(title: String, markdown: String, files: [String: Data]) throws -> String {
    let slug = slugify(title)
    guard !slug.isEmpty else {
      throw NSError(
        domain: "LocalSkillsStore", code: 1,
        userInfo: [NSLocalizedDescriptionKey: "Skill name must contain letters or numbers"])
    }
    let fm = FileManager.default
    let destination = skillsDirURL.appendingPathComponent(slug, isDirectory: true)
    try fm.createDirectory(at: skillsDirURL, withIntermediateDirectories: true)

    // Staged outside the skills folder so a crash mid-install cannot leave a directory the
    // catalog would read, and swapped in with `replaceItemAt` so the old version survives a
    // failure: deleting the destination first means a move that throws — a full disk, a denied
    // write — takes the working skill with it and leaves nothing.
    let staging = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
      .appendingPathComponent("omi-skill-\(slug)-\(UUID().uuidString)", isDirectory: true)
    try fm.createDirectory(at: staging, withIntermediateDirectories: true)
    defer { try? fm.removeItem(at: staging) }

    try Data(normalize(markdown: markdown, slug: slug).utf8)
      .write(to: staging.appendingPathComponent("SKILL.md"), options: .atomic)
    for (path, data) in files where path.caseInsensitiveCompare("SKILL.md") != .orderedSame {
      guard ExtensionCatalog.SkillSource.isSafe(path: path) else { continue }
      let file = staging.appendingPathComponent(path)
      try fm.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
      try data.write(to: file, options: .atomic)
    }

    if fm.fileExists(atPath: destination.path) {
      _ = try fm.replaceItemAt(destination, withItemAt: staging)
    } else {
      try fm.moveItem(at: staging, to: destination)
    }
    ensurePluginManifest()
    notifyChanged()
    return slug
  }

  static func deleteSkill(slug: String) {
    try? FileManager.default.removeItem(at: skillsDirURL.appendingPathComponent(slug))
    // The disabled set holds slugs; deleting a disabled skill would otherwise
    // leave a dead entry behind forever.
    var names = disabledSkillNames()
    if names.remove(slug) != nil {
      setDisabledSkillNames(names)
    }
    notifyChanged()
  }

  // MARK: - Disabled skills

  /// The set of slugs the user disabled in Settings, stored as a JSON array in
  /// `DefaultsKey.disabledSkillsJSON`. Owned here because the slug is this
  /// store's identity: rename and delete must keep the set in step. ChatProvider
  /// reads the toggle through this same parse, so the catalog, the task-chat
  /// projection, and the runtime's `OMI_DISABLED_SKILLS` env all agree.
  static func disabledSkillNames() -> Set<String> {
    guard let raw = UserDefaults.standard.string(forKey: DefaultsKey.disabledSkillsJSON),
      let data = raw.data(using: .utf8),
      let names = try? JSONDecoder().decode([String].self, from: data)
    else {
      return []  // Default: nothing disabled = all enabled
    }
    return Set(names)
  }

  static func setDisabledSkillNames(_ names: Set<String>) {
    // Sorted so the persisted JSON is stable for a given set.
    if let data = try? JSONEncoder().encode(names.sorted()),
      let json = String(data: data, encoding: .utf8)
    {
      UserDefaults.standard.set(json, forKey: DefaultsKey.disabledSkillsJSON)
    }
  }

  /// Rename bookkeeping for the disable toggle: the set holds slugs, so
  /// leaving the old slug behind would silently re-enable the renamed skill
  /// and let dead entries accumulate.
  private static func rekeyDisabledSlug(from oldSlug: String, to newSlug: String) {
    var names = disabledSkillNames()
    guard names.remove(oldSlug) != nil else { return }
    names.insert(newSlug)
    setDisabledSkillNames(names)
  }

  /// The ACP lane loads this directory as a local Claude plugin, which requires
  /// a `.claude-plugin/plugin.json` manifest at the root.
  static func ensurePluginManifest() {
    let fm = FileManager.default
    guard !fm.fileExists(atPath: pluginManifestURL.path) else { return }
    try? fm.createDirectory(at: pluginManifestURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try? Data(#"{"name": "omi-user-skills", "version": "1.0.0"}"#.utf8).write(to: pluginManifestURL, options: .atomic)
  }

  /// Runtime-spawn safety net: skills dropped by hand never run the UI save path,
  /// so without this the ACP lane would silently miss them. A no-op until the
  /// user actually has a skills folder.
  static func ensurePluginManifestIfSkillsExist() {
    guard FileManager.default.fileExists(atPath: skillsDirURL.path) else { return }
    ensurePluginManifest()
  }

  private static func notifyChanged() {
    if Thread.isMainThread {
      NotificationCenter.default.post(name: .omiUserSkillsDidChange, object: nil)
    } else {
      DispatchQueue.main.async {
        NotificationCenter.default.post(name: .omiUserSkillsDidChange, object: nil)
      }
    }
  }

  // MARK: - Markdown normalization

  /// Whether a file is an Agent Skill rather than any other Markdown. The format's whole contract
  /// is YAML frontmatter carrying a `description` — that string is what the model matches a request
  /// against, so a README imported without one is a skill that can never be selected.
  ///
  /// Only the *import* paths check this. Text typed or pasted into the editor is still normalized,
  /// because there the user is authoring the skill rather than claiming a file already is one.
  static func validationError(forImportedMarkdown markdown: String) -> String? {
    let (meta, body) = splitFrontmatter(of: markdown)
    guard !meta.isEmpty else {
      return "That file has no SKILL.md frontmatter. A skill starts with a --- block naming it."
    }
    guard let description = frontmatterValue(meta, key: "description"),
      !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return "That file's frontmatter has no description. The assistant needs one to know when to load the skill."
    }
    guard !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return "That file has frontmatter but no instructions under it."
    }
    return nil
  }

  static func normalize(markdown: String, slug: String) -> String {
    let (meta, body) = splitFrontmatter(of: markdown)
    var lines = ["name: \(slug)"]
    let description =
      frontmatterValue(meta, key: "description")
      ?? firstProseLine(of: body) ?? "User-authored skill"
    lines.append("description: \(description)")
    // Preserve author-written keys other than the two we own.
    for line in meta where !line.hasPrefix("name:") && !line.hasPrefix("description:") {
      lines.append(line)
    }
    let bodyText = body.trimmingCharacters(in: .whitespacesAndNewlines)
    return "---\n\(lines.joined(separator: "\n"))\n---\n\n\(bodyText)\n"
  }

  private static func splitFrontmatter(of content: String) -> (meta: [String], body: String) {
    let lines = content.components(separatedBy: "\n")
    guard lines.first?.trimmingCharacters(in: .whitespaces) == "---",
      let end = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "---" })
    else { return ([], content) }
    let meta = lines[1..<end].map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    let body = lines[(end + 1)...].joined(separator: "\n")
    return (meta, body)
  }

  private static func frontmatter(of content: String) -> [String: String] {
    var result: [String: String] = [:]
    for line in splitFrontmatter(of: content).meta {
      guard let colon = line.firstIndex(of: ":") else { continue }
      let key = String(line[..<colon]).trimmingCharacters(in: .whitespaces)
      var value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
      value = value.trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
      result[key] = value
    }
    return result
  }

  private static func frontmatterValue(_ meta: [String], key: String) -> String? {
    for line in meta where line.hasPrefix("\(key):") {
      let value = String(line.dropFirst(key.count + 1)).trimmingCharacters(in: .whitespaces)
        .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
      if !value.isEmpty { return value }
    }
    return nil
  }

  private static func firstProseLine(of content: String) -> String? {
    let body = splitFrontmatter(of: content).body
    for line in body.components(separatedBy: "\n") {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if !trimmed.isEmpty && !trimmed.hasPrefix("#") { return trimmed }
    }
    return nil
  }

  private static func displayName(slug: String, frontmatterName: String?) -> String {
    // The slug is the identity; render it human-readably.
    let base = frontmatterName.flatMap { $0.isEmpty ? nil : $0 } ?? slug
    return base.replacingOccurrences(of: "-", with: " ").capitalized
  }
}
