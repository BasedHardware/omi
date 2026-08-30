import Foundation

/// Fetches marketplace catalogs and installs what the user picks into `~/.omi`.
///
/// Every browse path is fail-open: a failure records a fallback and yields no entries, so the
/// Marketplace section empties while the installed lists keep working offline. Installs are the
/// opposite — they report their error, because a silent no-op after pressing Install is a lie.
enum ExtensionCatalogService {
  /// Long enough for a cold registry, short enough that a hung catalog never holds the section.
  static let requestTimeout: TimeInterval = 12

  /// Caps on a skill folder, which is remote input: enough for the largest catalog skill today
  /// (80-odd font files) without letting a hostile repo write a disk's worth into `~/.omi`.
  static let maxSkillFiles = 200
  static let maxSkillFileBytes = 4 * 1024 * 1024
  static let maxSkillBundleBytes = 32 * 1024 * 1024

  enum CatalogError: LocalizedError {
    case unreachable
    case emptySkill

    var errorDescription: String? {
      switch self {
      case .unreachable: return "Could not reach the catalog. Check your connection and try again."
      case .emptySkill: return "That skill's SKILL.md was empty."
      }
    }
  }

  // MARK: - Browse

  /// With no query the user sees the curated featured servers rather than the registry's
  /// alphabetical listing; typing searches the whole registry.
  static func mcpEntries(search: String) async -> [ExtensionCatalog.Entry] {
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    return query.isEmpty ? await featuredMcpEntries() : await searchMcpEntries(search: query)
  }

  /// Each featured server is fetched by exact name and independently: one unpublished or renamed
  /// entry costs its own tile, never the rest of the section.
  static func featuredMcpEntries() async -> [ExtensionCatalog.Entry] {
    guard
      let baseURL = ExtensionCatalog.sources(kind: .mcp).compactMap({ source -> URL? in
        if case .mcpRegistry(let url) = source.feed { return url }
        return nil
      }).first
    else { return [] }
    let featured = ExtensionCatalog.featuredMcpServers
    let resolved = await withTaskGroup(of: (Int, ExtensionCatalog.Entry?).self) { group in
      for (index, server) in featured.enumerated() {
        group.addTask {
          guard let url = versionsURL(base: baseURL, serverName: server.name),
            let data = await get(url, area: "extension_catalog_mcp_featured")
          else { return (index, nil) }
          return (
            index,
            ExtensionCatalog.mcpEntry(fromVersions: data, name: server.name, title: server.title)
          )
        }
      }
      var byIndex: [Int: ExtensionCatalog.Entry] = [:]
      for await (index, entry) in group { byIndex[index] = entry }
      return byIndex
    }
    // Curated order, not completion order.
    return featured.indices.compactMap { resolved[$0] }
  }

  static func versionsURL(base: URL, serverName: String) -> URL? {
    guard
      let escaped = serverName.addingPercentEncoding(
        withAllowedCharacters: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~")))
    else { return nil }
    return URL(string: "/v0/servers/\(escaped)/versions", relativeTo: base)?.absoluteURL
  }

  static func searchMcpEntries(search: String) async -> [ExtensionCatalog.Entry] {
    var entries: [ExtensionCatalog.Entry] = []
    for source in ExtensionCatalog.sources(kind: .mcp) {
      guard case .mcpRegistry(let baseURL) = source.feed else { continue }
      guard let url = registryURL(base: baseURL, search: search),
        let data = await get(url, area: "extension_catalog_mcp")
      else { continue }
      entries += ExtensionCatalog.mcpEntries(fromRegistry: data)
    }
    return entries
  }

  static func skillEntries(search: String) async -> [ExtensionCatalog.Entry] {
    var entries: [ExtensionCatalog.Entry] = []
    for source in ExtensionCatalog.sources(kind: .skill) {
      guard case .githubSkillsRepo(let repo, let ref) = source.feed else { continue }
      guard
        let url = URL(
          string: "https://api.github.com/repos/\(repo)/git/trees/\(ref)?recursive=1"),
        let data = await get(url, area: "extension_catalog_skills")
      else { continue }
      let listed = ExtensionCatalog.skillEntries(fromRepoTree: data, repo: repo, ref: ref)
      entries += await withDescriptions(listed)
    }
    // The index has no server-side search, so the query filters what came back.
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !query.isEmpty else { return entries }
    return entries.filter {
      $0.name.localizedCaseInsensitiveContains(query)
        || $0.detail.localizedCaseInsensitiveContains(query)
    }
  }

  /// Each catalog skill's own description, fetched from its SKILL.md. Without these every tile
  /// reads "Agent skill from <repo>", which tells a user nothing about which one they want. Keyed
  /// by slug; a skill whose file will not load simply keeps the fallback text.
  private static func withDescriptions(_ entries: [ExtensionCatalog.Entry]) async
    -> [ExtensionCatalog.Entry]
  {
    let found = await withTaskGroup(of: (String, String)?.self) { group in
      for entry in entries {
        guard case .skill(let source) = entry.install, let url = source.markdownURL else { continue }
        group.addTask {
          guard let data = await get(url, area: "extension_catalog_skill_description"),
            let markdown = String(data: data, encoding: .utf8),
            let description = ExtensionCatalog.skillDescription(fromMarkdown: markdown)
          else { return nil }
          return (entry.id, description)
        }
      }
      var byID: [String: String] = [:]
      for await pair in group { if let pair { byID[pair.0] = pair.1 } }
      return byID
    }
    return entries.map { entry in
      guard let description = found[entry.id] else { return entry }
      var updated = entry
      updated.detail = description
      return updated
    }
  }

  static func registryURL(base: URL, search: String) -> URL? {
    var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
    components?.path = "/v0/servers"
    var items = [
      URLQueryItem(name: "limit", value: "50"),
      URLQueryItem(name: "version", value: "latest"),
    ]
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    if !query.isEmpty { items.append(URLQueryItem(name: "search", value: query)) }
    components?.queryItems = items
    return components?.url
  }

  private static func get(_ url: URL, area: String) async -> Data? {
    var request = URLRequest(url: url, timeoutInterval: requestTimeout)
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    do {
      let (data, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
        recordCatalogFallback(area: area, reason: "http_status")
        return nil
      }
      return data
    } catch {
      recordCatalogFallback(area: area, reason: "request_failed")
      return nil
    }
  }

  private static func recordCatalogFallback(area: String, reason: String) {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: area, from: "catalog", to: "installed_only", reason: reason, outcome: .degraded)
  }

  // MARK: - Install

  /// Writes the entry into `~/.omi`. `secrets` fills the env variables or auth header the entry
  /// declared it needs; an entry with `install.needsInput == false` takes an empty dictionary.
  static func install(_ entry: ExtensionCatalog.Entry, secrets: [String: String] = [:]) async throws {
    switch entry.install {
    case .mcpRemote(let url, let transport, let secretHeader):
      var raw: [String: Any] = ["url": url, "transport": transport]
      if let secretHeader, let token = nonEmpty(secrets[secretHeader]) {
        raw["headers"] = [secretHeader: authorizationValue(header: secretHeader, secret: token)]
      }
      try LocalMcpStore.upsertServer(availableServerName(for: entry.name), entry: raw)

    case .mcpStdio(let command, let args, let requiredEnv):
      var raw: [String: Any] = ["command": command, "args": args]
      let env = requiredEnv.reduce(into: [String: String]()) { result, name in
        if let value = nonEmpty(secrets[name]) { result[name] = value }
      }
      if !env.isEmpty { raw["env"] = env }
      try LocalMcpStore.upsertServer(availableServerName(for: entry.name), entry: raw)

    case .skill(let source):
      guard let markdownURL = source.markdownURL,
        let data = await get(markdownURL, area: "extension_catalog_skill_body"),
        let markdown = String(data: data, encoding: .utf8)
      else { throw CatalogError.unreachable }
      guard !markdown.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        throw CatalogError.emptySkill
      }
      let files = await bundledFiles(of: source)
      _ = try LocalSkillsStore.saveSkillBundle(
        title: entry.name, markdown: markdown, files: files)
    }
  }

  /// A skill's non-Markdown files: the scripts, references and assets its instructions point at.
  ///
  /// Fetched concurrently and capped, because a catalog folder is remote input of unknown size —
  /// one repo's skill ships 80 font files. A file that will not load is left out rather than
  /// failing the install: a skill missing one reference is still usable, and the alternative is
  /// that one dead blob costs the user the whole skill.
  static func bundledFiles(of source: ExtensionCatalog.SkillSource) async -> [String: Data] {
    let paths = source.files.filter { $0 != "SKILL.md" }.prefix(maxSkillFiles)
    let fetched = await withTaskGroup(of: (String, Data)?.self) { group in
      for path in paths {
        guard let url = source.rawURL(for: path) else { continue }
        group.addTask {
          guard let data = await get(url, area: "extension_catalog_skill_file"),
            data.count <= maxSkillFileBytes
          else { return nil }
          return (path, data)
        }
      }
      var byPath: [String: Data] = [:]
      var total = 0
      for await pair in group {
        guard let pair, total + pair.1.count <= maxSkillBundleBytes else { continue }
        total += pair.1.count
        byPath[pair.0] = pair.1
      }
      return byPath
    }
    return fetched
  }

  /// An `Authorization` header carries a scheme; a user pasting a key types only the key. Storing
  /// it bare sends a malformed header that the server rejects as unauthenticated.
  static func authorizationValue(header: String, secret: String) -> String {
    guard header.caseInsensitiveCompare("Authorization") == .orderedSame else { return secret }
    let known = ["bearer ", "basic ", "token "]
    let lowered = secret.lowercased()
    return known.contains(where: lowered.hasPrefix) ? secret : "Bearer \(secret)"
  }

  private static func nonEmpty(_ value: String?) -> String? {
    guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty
    else { return nil }
    return trimmed
  }

  /// Installing must never silently overwrite a server the user configured by hand, so a taken
  /// name gains a numeric suffix instead.
  static func availableServerName(for displayName: String, taken: Set<String>? = nil) -> String {
    let existing = taken ?? Set(LocalMcpStore.readAllServers().keys)
    let base = LocalSkillsStore.slugify(displayName)
    let root = base.isEmpty ? "server" : base
    guard existing.contains(root) else { return root }
    var suffix = 2
    while existing.contains("\(root)-\(suffix)") { suffix += 1 }
    return "\(root)-\(suffix)"
  }
}
