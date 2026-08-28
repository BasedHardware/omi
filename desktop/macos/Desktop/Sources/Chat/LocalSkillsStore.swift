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
    return dirs.sorted().compactMap { slug in
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
    }
    ensurePluginManifest()
    notifyChanged()
    return slug
  }

  static func deleteSkill(slug: String) {
    try? FileManager.default.removeItem(at: skillsDirURL.appendingPathComponent(slug))
    notifyChanged()
  }

  /// The ACP lane loads this directory as a local Claude plugin, which requires
  /// a `.claude-plugin/plugin.json` manifest at the root.
  static func ensurePluginManifest() {
    let fm = FileManager.default
    let manifestDir = rootURL.appendingPathComponent(".claude-plugin", isDirectory: true)
    let manifest = manifestDir.appendingPathComponent("plugin.json")
    guard !fm.fileExists(atPath: manifest.path) else { return }
    try? fm.createDirectory(at: manifestDir, withIntermediateDirectories: true)
    try? Data(#"{"name": "omi-user-skills", "version": "1.0.0"}"#.utf8).write(to: manifest, options: .atomic)
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
