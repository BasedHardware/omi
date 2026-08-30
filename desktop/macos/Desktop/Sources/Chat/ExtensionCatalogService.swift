import Foundation

/// Fetches marketplace catalogs and installs what the user picks into `~/.omi`.
///
/// Every browse path is fail-open: a failure records a fallback and yields no entries, so the
/// Marketplace section empties while the installed lists keep working offline. Installs are the
/// opposite — they report their error, because a silent no-op after pressing Install is a lie.
enum ExtensionCatalogService {
  /// Long enough for a cold registry, short enough that a hung catalog never holds the section.
  static let requestTimeout: TimeInterval = 12

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
    // Curated first-party servers lead, then Smithery's verified and ranked list. Both registries
    // contribute in both modes: the curated names are the ones a user recognises, and Smithery is
    // the only source with a verification flag and a usage signal to rank the rest by.
    async let leadingTask = query.isEmpty ? featuredMcpEntries() : searchMcpEntries(search: query)
    async let smitheryTask = smitheryEntries(search: query)
    var entries = await leadingTask
    var seen = Set(entries.map { $0.name.lowercased() })
    for entry in await smitheryTask where seen.insert(entry.name.lowercased()).inserted {
      entries.append(entry)
    }
    return entries
  }

  /// Verified, deployed Smithery servers. The listing carries no endpoint, so each candidate's
  /// detail is fetched concurrently; a candidate whose detail fails is dropped rather than shown as
  /// a tile that cannot install.
  static func smitheryEntries(search: String, limit: Int = 24) async -> [ExtensionCatalog.Entry] {
    guard
      let baseURL = ExtensionCatalog.sources(kind: .mcp).compactMap({ source -> URL? in
        if case .smithery(let url) = source.feed { return url }
        return nil
      }).first
    else { return [] }
    guard let listing = smitheryListingURL(base: baseURL, search: search, limit: limit),
      let data = await get(listing, area: "extension_catalog_smithery")
    else { return [] }

    let candidates = ExtensionCatalog.smitheryCandidates(fromListing: data)
    let resolved = await withTaskGroup(of: (Int, ExtensionCatalog.Entry?).self) { group in
      for (index, candidate) in candidates.enumerated() {
        group.addTask {
          guard let url = smitheryDetailURL(base: baseURL, qualifiedName: candidate.qualifiedName),
            let detail = await get(url, area: "extension_catalog_smithery_detail")
          else { return (index, nil) }
          return (index, ExtensionCatalog.smitheryEntry(fromDetail: detail, candidate: candidate))
        }
      }
      var byIndex: [Int: ExtensionCatalog.Entry] = [:]
      for await (index, entry) in group { byIndex[index] = entry }
      return byIndex
    }
    // Registry ranking, not completion order.
    return candidates.indices.compactMap { resolved[$0] }
  }

  static func smitheryListingURL(base: URL, search: String, limit: Int) -> URL? {
    var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
    components?.path = "/servers"
    var items = [URLQueryItem(name: "pageSize", value: String(limit))]
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    if !query.isEmpty { items.append(URLQueryItem(name: "q", value: query)) }
    components?.queryItems = items
    return components?.url
  }

  static func smitheryDetailURL(base: URL, qualifiedName: String) -> URL? {
    let escaped =
      qualifiedName.addingPercentEncoding(
        withAllowedCharacters: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~/")))
      ?? qualifiedName
    return URL(string: "/servers/\(escaped)", relativeTo: base)?.absoluteURL
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
        let url = URL(string: "https://api.github.com/repos/\(repo)/contents/skills?ref=\(ref)"),
        let data = await get(url, area: "extension_catalog_skills")
      else { continue }
      let listed = ExtensionCatalog.skillEntries(fromRepoContents: data, repo: repo, ref: ref)
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
        guard case .skill(let url) = entry.install else { continue }
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
        raw["headers"] = [secretHeader: token]
      }
      try LocalMcpStore.upsertServer(availableServerName(for: entry.name), entry: raw)

    case .mcpStdio(let command, let args, let requiredEnv):
      var raw: [String: Any] = ["command": command, "args": args]
      let env = requiredEnv.reduce(into: [String: String]()) { result, name in
        if let value = nonEmpty(secrets[name]) { result[name] = value }
      }
      if !env.isEmpty { raw["env"] = env }
      try LocalMcpStore.upsertServer(availableServerName(for: entry.name), entry: raw)

    case .skill(let markdownURL):
      guard let data = await get(markdownURL, area: "extension_catalog_skill_body"),
        let markdown = String(data: data, encoding: .utf8)
      else { throw CatalogError.unreachable }
      guard !markdown.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        throw CatalogError.emptySkill
      }
      _ = try LocalSkillsStore.saveSkill(title: entry.name, markdown: markdown)
    }
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
