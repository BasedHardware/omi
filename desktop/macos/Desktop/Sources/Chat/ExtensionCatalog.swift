import Foundation

/// Browsable catalogs of MCP servers and skills the user has not installed yet.
///
/// Both feeds are read-only and fail-open: a catalog that is unreachable, slow, or malformed
/// yields no entries and leaves the installed lists — which are pure local disk reads — untouched.
/// Nothing here can break chat; the worst case is a missing Marketplace section.
///
/// Sources live in `~/.omi/catalogs.json` so an org can point at an internal index, and are
/// hand-editable like the rest of `~/.omi`. Absent or unparseable file means the defaults below.
enum ExtensionCatalog {
  enum Kind: String {
    case mcp
    case skill
  }

  /// What installing an entry writes. Resolved at browse time so the install itself is a local
  /// file write with no second network round trip that could fail half-way.
  enum Install: Equatable {
    /// A remote MCP endpoint. `secretHeader` names the header its auth needs, when it needs one.
    case mcpRemote(url: String, transport: String, secretHeader: String?)
    /// A local MCP command. `requiredEnv` are variables the server declares it cannot run without.
    case mcpStdio(command: String, args: [String], requiredEnv: [String])
    /// A skill's raw `SKILL.md`, fetched on install.
    case skill(markdownURL: URL)

    var needsInput: Bool {
      switch self {
      case .mcpRemote(_, _, let header): return header != nil
      case .mcpStdio(_, _, let env): return !env.isEmpty
      case .skill: return false
      }
    }
  }

  struct Entry: Identifiable, Equatable {
    let id: String
    let name: String
    /// Transport or origin, shown where an installed card shows "Local command".
    let subtitle: String
    var detail: String
    /// Publisher logo. Empty when the entry offers no usable image and the card falls back to its
    /// symbol; never a guess that would render a broken tile.
    var iconURL: String = ""
    /// Homepage or docs, shown in the detail sheet so a user can read up before installing.
    var websiteURL: String?
    /// The publisher identity the registry verified — the reverse-DNS namespace owns that domain.
    var publisher: String = ""
    let install: Install
  }

  // MARK: - Featured servers

  /// The registry has no popularity, rating, or curation signal — its listing is alphabetical over
  /// thousands of entries, and a vendor namespace only proves the publisher owns *some* domain, not
  /// that anyone has heard of it. Browsing it raw shows the user noise.
  ///
  /// So the default view is this list: servers published under their own brand's DNS-verified
  /// namespace, each confirmed present in the registry. Search still queries the whole registry;
  /// this only decides what a user sees before they type. Install data always comes from the
  /// registry, never from here — these are names and titles, not configuration.
  static let featuredMcpServers: [(name: String, title: String)] = [
    ("app.linear/linear", "Linear"),
    ("com.notion/mcp", "Notion"),
    ("com.stripe/mcp", "Stripe"),
    ("com.figma.mcp/mcp", "Figma"),
    ("com.atlassian/atlassian-mcp-server", "Atlassian"),
    ("com.supabase/mcp", "Supabase"),
    ("com.cloudflare.mcp/mcp", "Cloudflare"),
    ("com.vercel/vercel-mcp", "Vercel"),
    ("com.zapier/mcp", "Zapier"),
    ("com.webflow/mcp", "Webflow"),
    ("com.airtable/mcp", "Airtable"),
    ("com.monday/monday.com", "monday.com"),
    ("com.paypal.mcp/mcp", "PayPal"),
    ("com.wix/mcp", "Wix"),
    ("com.apify/apify-mcp-server", "Apify"),
    ("ai.exa/exa", "Exa"),
    ("io.snyk/mcp", "Snyk"),
  ]

  // MARK: - Sources

  struct Source: Equatable {
    enum Feed: Equatable {
      /// The official MCP Registry API (`/v0/servers`).
      case mcpRegistry(baseURL: URL)
      /// A GitHub repository laid out like `anthropics/skills`: one `skills/<slug>/SKILL.md` each.
      case githubSkillsRepo(repo: String, ref: String)
      /// Smithery's registry, which unlike the official one publishes a verification flag, a usage
      /// count, and an icon per server — the ranking signals that decide what is worth showing.
      case smithery(baseURL: URL)
    }

    let kind: Kind
    let feed: Feed
  }

  static let defaultSources: [Source] = [
    Source(kind: .mcp, feed: .smithery(baseURL: URL(string: "https://registry.smithery.ai")!)),
    Source(
      kind: .mcp,
      feed: .mcpRegistry(baseURL: URL(string: "https://registry.modelcontextprotocol.io")!)),
    Source(kind: .skill, feed: .githubSkillsRepo(repo: "anthropics/skills", ref: "main")),
    Source(kind: .skill, feed: .githubSkillsRepo(repo: "obra/superpowers", ref: "main")),
  ]

  static var configURL: URL { LocalSkillsStore.rootURL.appendingPathComponent("catalogs.json") }

  /// Sources for one kind, from `~/.omi/catalogs.json`, falling back to the defaults. A file that
  /// lists catalogs for only one kind still gets the default for the other.
  static func sources(kind: Kind, configURL: URL? = nil) -> [Source] {
    let url = configURL ?? Self.configURL
    guard let data = try? Data(contentsOf: url),
      let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let raw = root["catalogs"] as? [[String: Any]]
    else {
      return defaultSources.filter { $0.kind == kind }
    }

    let parsed = raw.compactMap { source(from: $0) }.filter { $0.kind == kind }
    return parsed.isEmpty ? defaultSources.filter { $0.kind == kind } : parsed
  }

  static func source(from raw: [String: Any]) -> Source? {
    guard let kind = (raw["kind"] as? String).flatMap(Kind.init(rawValue:)) else { return nil }
    switch raw["type"] as? String {
    case "mcp-registry":
      guard let url = (raw["url"] as? String).flatMap(URL.init(string:)) else { return nil }
      return Source(kind: kind, feed: .mcpRegistry(baseURL: url))
    case "smithery":
      guard let url = (raw["url"] as? String).flatMap(URL.init(string:)) else { return nil }
      return Source(kind: kind, feed: .smithery(baseURL: url))
    case "github-skills":
      guard let repo = raw["repo"] as? String, !repo.isEmpty else { return nil }
      return Source(kind: kind, feed: .githubSkillsRepo(repo: repo, ref: raw["ref"] as? String ?? "main"))
    default:
      return nil
    }
  }

  // MARK: - MCP registry decoding

  /// Newest-version-wins by server name. The registry returns one record per published version, so
  /// listing it raw shows the same server three times.
  static func mcpEntries(fromRegistry data: Data) -> [Entry] {
    guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let servers = root["servers"] as? [[String: Any]]
    else { return [] }

    var byName: [String: Entry] = [:]
    var order: [String] = []
    for record in servers {
      guard let server = record["server"] as? [String: Any],
        let name = server["name"] as? String, !name.isEmpty,
        let entry = mcpEntry(from: server, qualifiedName: name)
      else { continue }
      if byName.updateValue(entry, forKey: name) == nil { order.append(name) }
    }
    return order.compactMap { byName[$0] }
  }

  private static func mcpEntry(
    from server: [String: Any], qualifiedName: String, titleOverride: String? = nil
  ) -> Entry? {
    let detail = (server["description"] as? String) ?? ""
    // Registry names are reverse-DNS qualified ("io.github.owner/thing"); the last path segment is
    // what a user recognises, and is also what has to survive `slugify` as a local server name.
    let display =
      titleOverride
      ?? (server["title"] as? String).flatMap { $0.isEmpty ? nil : $0 }
      ?? String(qualifiedName.split(separator: "/").last ?? Substring(qualifiedName))
    let website = (server["websiteUrl"] as? String).flatMap { $0.isEmpty ? nil : $0 }
    let icon = iconURL(for: server, websiteURL: website)
    let publisher = String(qualifiedName.split(separator: "/").first ?? Substring(qualifiedName))

    if let remotes = server["remotes"] as? [[String: Any]], let remote = remotes.first,
      let url = remote["url"] as? String, !url.isEmpty
    {
      let transport = (remote["type"] as? String) == "sse" ? "sse" : "http"
      let headers = (remote["headers"] as? [[String: Any]]) ?? []
      let secretHeader = headers.compactMap { $0["name"] as? String }
        .first { $0.caseInsensitiveCompare("Authorization") == .orderedSame }
      return Entry(
        id: qualifiedName, name: display, subtitle: "Remote", detail: detail, iconURL: icon,
        websiteURL: website, publisher: publisher,
        install: .mcpRemote(url: url, transport: transport, secretHeader: secretHeader))
    }

    if let packages = server["packages"] as? [[String: Any]],
      let package = packages.first(where: { ($0["transport"] as? [String: Any])?["type"] as? String == "stdio" })
        ?? packages.first,
      let invocation = stdioInvocation(for: package)
    {
      let requiredEnv = ((package["environmentVariables"] as? [[String: Any]]) ?? [])
        .filter { ($0["isRequired"] as? Bool) == true }
        .compactMap { $0["name"] as? String }
      return Entry(
        id: qualifiedName, name: display, subtitle: "Local command", detail: detail, iconURL: icon,
        websiteURL: website, publisher: publisher,
        install: .mcpStdio(
          command: invocation.command, args: invocation.args, requiredEnv: requiredEnv))
    }

    return nil
  }

  /// Publisher logo, best available source first. Every candidate is a URL the publisher itself
  /// controls — no third-party favicon proxy, which would leak which servers a user browses.
  /// Returns "" rather than a guess when nothing is available, so the card shows its symbol
  /// instead of a broken tile.
  static func iconURL(for server: [String: Any], websiteURL: String?) -> String {
    // 1. What the publisher declared. The spec requires HTTPS; anything else is not rendered.
    if let icons = server["icons"] as? [[String: Any]],
      let src = icons.compactMap({ $0["src"] as? String }).first(where: { $0.hasPrefix("https://") })
    {
      return src
    }
    // 2. A GitHub-hosted server: the owner's avatar is stable and always present.
    if let repo = server["repository"] as? [String: Any],
      let url = repo["url"] as? String,
      let owner = gitHubOwner(fromRepositoryURL: url)
    {
      return "https://github.com/\(owner).png?size=128"
    }
    // 3. The brand's own favicon. Not every site serves one; a miss renders as the symbol.
    if let host = websiteURL.flatMap({ URL(string: $0)?.host }) {
      return "https://\(host)/favicon.ico"
    }
    return ""
  }

  static func gitHubOwner(fromRepositoryURL raw: String) -> String? {
    guard let url = URL(string: raw), url.host?.hasSuffix("github.com") == true else { return nil }
    let owner = url.pathComponents.dropFirst().first ?? ""
    return owner.isEmpty ? nil : owner
  }

  /// One server's newest published version, from `/v0/servers/{name}/versions`.
  static func mcpEntry(fromVersions data: Data, name: String, title: String?) -> Entry? {
    guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let records = root["servers"] as? [[String: Any]], !records.isEmpty
    else { return nil }
    let latest =
      records.last(where: {
        (($0["_meta"] as? [String: Any])?["io.modelcontextprotocol.registry/official"]
          as? [String: Any])?["isLatest"] as? Bool == true
      }) ?? records[records.count - 1]
    guard let server = latest["server"] as? [String: Any] else { return nil }
    return mcpEntry(from: server, qualifiedName: name, titleOverride: title)
  }

  /// npm/PyPI packages map onto the launcher their `runtimeHint` names. Anything else (OCI images,
  /// unknown registries) is skipped rather than guessed at — a wrong command is a dead server the
  /// user has to debug, which is worse than not offering it.
  private static func stdioInvocation(for package: [String: Any]) -> (command: String, args: [String])? {
    guard let identifier = package["identifier"] as? String, !identifier.isEmpty else { return nil }
    let version = (package["version"] as? String).flatMap { $0.isEmpty ? nil : $0 }
    let runtime = (package["runtimeHint"] as? String) ?? defaultRuntime(for: package["registryType"] as? String)
    guard let runtime, runtime == "npx" || runtime == "uvx" else { return nil }

    let runtimeArgs = argumentValues(package["runtimeArguments"])
    let packageArgs = argumentValues(package["packageArguments"])
    let spec = version.map { "\(identifier)@\($0)" } ?? identifier
    return (runtime, runtimeArgs + [spec] + packageArgs)
  }

  private static func defaultRuntime(for registryType: String?) -> String? {
    switch registryType {
    case "npm": return "npx"
    case "pypi": return "uvx"
    default: return nil
    }
  }

  /// Only positional arguments carrying a literal value are safe to replay unattended; named
  /// arguments and user-supplied placeholders need input this list cannot supply.
  private static func argumentValues(_ raw: Any?) -> [String] {
    guard let arguments = raw as? [[String: Any]] else { return [] }
    return arguments.compactMap { argument in
      guard (argument["type"] as? String) ?? "positional" == "positional",
        let value = argument["value"] as? String, !value.isEmpty,
        !value.contains("{")
      else { return nil }
      return value
    }
  }

  // MARK: - Smithery decoding

  /// Smithery lists a server before saying how to reach it, so a listing row is only a candidate:
  /// `deploymentUrl` arrives with the per-server detail the service fetches next.
  struct SmitheryCandidate: Equatable {
    let qualifiedName: String
    let displayName: String
    let description: String
    let iconURL: String
    let homepage: String?
    let useCount: Int
  }

  /// Unverified entries are dropped. Anyone can publish, and an unvetted server is a command or a
  /// credentialed endpoint the user would be trusting on our recommendation.
  static func smitheryCandidates(fromListing data: Data) -> [SmitheryCandidate] {
    guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let servers = root["servers"] as? [[String: Any]]
    else { return [] }
    return servers.compactMap { server in
      guard let name = server["qualifiedName"] as? String, !name.isEmpty,
        server["verified"] as? Bool == true,
        server["inactive"] as? Bool != true,
        server["unlisted"] as? Bool != true,
        // Only deployed remotes are installable here; a Smithery-hosted local package is not
        // something this app can run.
        server["remote"] as? Bool == true, server["isDeployed"] as? Bool == true
      else { return nil }
      let icon = (server["iconUrl"] as? String).flatMap { $0.hasPrefix("https://") ? $0 : nil } ?? ""
      return SmitheryCandidate(
        qualifiedName: name,
        displayName: (server["displayName"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? name,
        description: (server["description"] as? String) ?? "",
        iconURL: icon,
        homepage: (server["homepage"] as? String).flatMap { $0.isEmpty ? nil : $0 },
        useCount: server["useCount"] as? Int ?? 0)
    }
  }

  /// The candidate plus its endpoint. Config the server declares required becomes the sheet's
  /// fields; Smithery servers are OAuth-protected resources, so most declare none and authorize on
  /// first connect.
  static func smitheryEntry(fromDetail data: Data, candidate: SmitheryCandidate) -> Entry? {
    guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      return nil
    }
    let connections = (root["connections"] as? [[String: Any]]) ?? []
    let httpConnection = connections.first { ($0["type"] as? String) == "http" } ?? connections.first
    guard
      let deployment = (httpConnection?["deploymentUrl"] as? String)
        ?? (root["deploymentUrl"] as? String), !deployment.isEmpty
    else { return nil }

    return Entry(
      id: "smithery/\(candidate.qualifiedName)",
      name: candidate.displayName,
      subtitle: "Remote",
      detail: candidate.description,
      iconURL: candidate.iconURL,
      websiteURL: candidate.homepage,
      publisher: "smithery.ai",
      // No key is asked for even when the server declares required config: Smithery servers are
      // OAuth-protected resources, and that config is collected by Smithery's own consent screen,
      // not sent by us as a header. Asking for it here would prompt for a value the user does not
      // have and store it somewhere it does nothing.
      install: .mcpRemote(url: deployment, transport: "http", secretHeader: nil))
  }

  // MARK: - GitHub skills repo decoding

  /// A skill's own `description:` frontmatter — the line the model matches a request against, and
  /// the only thing that tells one catalog tile from another. The repo index does not carry it, so
  /// the service fetches each SKILL.md and passes what it found; a miss falls back to the repo.
  static func skillDescription(fromMarkdown markdown: String) -> String? {
    let lines = markdown.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
    guard lines.first?.trimmingCharacters(in: .whitespaces) == "---" else { return nil }

    for (index, line) in lines.enumerated().dropFirst() {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if trimmed == "---" { return nil }
      guard trimmed.lowercased().hasPrefix("description:") else { continue }

      let inline = trimmed.dropFirst("description:".count).trimmingCharacters(in: .whitespaces)
      // A YAML block scalar (`description: >` / `|-`) keeps its text on the following indented
      // lines; taking the same line would show the user a lone ">".
      guard ["|", ">", "|-", ">-", "|+", ">+"].contains(inline) else {
        let unquoted = inline.trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
        return unquoted.isEmpty ? nil : unquoted
      }
      return foldedBlock(of: lines, startingAfter: index)
    }
    return nil
  }

  /// The indented body of a YAML block scalar, folded to one line — these are prose descriptions,
  /// and a card shows them on a single row either way.
  private static func foldedBlock(of lines: [String], startingAfter index: Int) -> String? {
    var collected: [String] = []
    for line in lines.dropFirst(index + 1) {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if trimmed == "---" { break }
      // Any unindented, non-empty line has ended the block and begun the next key.
      if !trimmed.isEmpty, !line.hasPrefix(" "), !line.hasPrefix("\t") { break }
      if trimmed.isEmpty, !collected.isEmpty { break }
      if !trimmed.isEmpty { collected.append(trimmed) }
    }
    let folded = collected.joined(separator: " ")
    return folded.isEmpty ? nil : folded
  }

  static func skillEntries(fromRepoContents data: Data, repo: String, ref: String) -> [Entry] {
    guard let items = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else { return [] }
    return items.compactMap { item in
      guard (item["type"] as? String) == "dir", let slug = item["name"] as? String, !slug.isEmpty
      else { return nil }
      guard
        let url = URL(
          string: "https://raw.githubusercontent.com/\(repo)/\(ref)/skills/\(slug)/SKILL.md")
      else { return nil }
      let owner = String(repo.split(separator: "/").first ?? Substring(repo))
      return Entry(
        id: "\(repo)/\(slug)",
        name: slug.replacingOccurrences(of: "-", with: " ").capitalized,
        subtitle: repo,
        detail: "Agent skill from \(repo).",
        iconURL: "https://github.com/\(owner).png?size=128",
        websiteURL: "https://github.com/\(repo)/tree/\(ref)/skills/\(slug)",
        publisher: owner,
        install: .skill(markdownURL: url))
    }
  }
}
