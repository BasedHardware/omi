import XCTest

@testable import Omi_Computer

/// The marketplace decodes third-party payloads it does not control, and the only thing standing
/// between a malformed record and a dead server the user has to debug is what this file asserts.
final class ExtensionCatalogTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory

  override func setUpWithError() throws {
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-catalog-test-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = tempRoot
  }

  override func tearDownWithError() throws {
    LocalSkillsStore.rootURLOverride = nil
    try? FileManager.default.removeItem(at: tempRoot)
  }

  // MARK: - MCP registry

  /// The registry publishes one record per version, so a raw listing repeats every server. The
  /// user must see each server once, at its newest published version.
  func testRegistryKeepsOneEntryPerServerName() throws {
    let payload = """
      {"servers": [
        {"server": {"name": "io.example/thing", "title": "Thing", "description": "v1",
                    "remotes": [{"type": "streamable-http", "url": "https://a.example/mcp"}]}},
        {"server": {"name": "io.example/thing", "title": "Thing", "description": "v2",
                    "remotes": [{"type": "streamable-http", "url": "https://b.example/mcp"}]}}
      ]}
      """
    let entries = ExtensionCatalog.mcpEntries(fromRegistry: Data(payload.utf8))

    XCTAssertEqual(entries.count, 1)
    XCTAssertEqual(entries[0].detail, "v2")
    XCTAssertEqual(
      entries[0].install, .mcpRemote(url: "https://b.example/mcp", transport: "http", secretHeader: nil))
  }

  func testRegistryMapsNpmPackageToNpxCommand() throws {
    let payload = """
      {"servers": [{"server": {"name": "io.example/pkg", "description": "d", "packages": [
        {"registryType": "npm", "identifier": "some-mcp", "version": "1.2.3", "runtimeHint": "npx",
         "transport": {"type": "stdio"},
         "runtimeArguments": [{"value": "-y", "type": "positional"}],
         "environmentVariables": [{"name": "API_KEY", "isRequired": true},
                                  {"name": "OPTIONAL", "isRequired": false}]}
      ]}}]}
      """
    let entries = ExtensionCatalog.mcpEntries(fromRegistry: Data(payload.utf8))

    XCTAssertEqual(
      entries.first?.install,
      .mcpStdio(command: "npx", args: ["-y", "some-mcp@1.2.3"], requiredEnv: ["API_KEY"]))
    XCTAssertEqual(entries.first?.name, "pkg", "reverse-DNS names must show their last segment")
    XCTAssertTrue(entries.first?.install.needsInput ?? false)
  }

  /// A runtime we cannot launch, or an argument carrying a `{placeholder}` we cannot fill, would
  /// install a command that fails the first time it runs. Offering nothing is the better failure.
  func testRegistrySkipsUnlaunchablePackagesAndPlaceholderArguments() throws {
    let ociOnly = """
      {"servers": [{"server": {"name": "io.example/img", "description": "d", "packages": [
        {"registryType": "oci", "identifier": "example/img", "version": "1"}]}}]}
      """
    XCTAssertTrue(ExtensionCatalog.mcpEntries(fromRegistry: Data(ociOnly.utf8)).isEmpty)

    let placeholder = """
      {"servers": [{"server": {"name": "io.example/pkg", "description": "d", "packages": [
        {"registryType": "npm", "identifier": "some-mcp", "runtimeHint": "npx",
         "packageArguments": [{"value": "{path}", "type": "positional"},
                              {"value": "--safe", "type": "positional"}]}]}}]}
      """
    XCTAssertEqual(
      ExtensionCatalog.mcpEntries(fromRegistry: Data(placeholder.utf8)).first?.install,
      .mcpStdio(command: "npx", args: ["some-mcp", "--safe"], requiredEnv: []))
  }

  /// Registry `io.snyk/mcp` declares `-t stdio` as a named argument. Dropping the flag launched
  /// `npx snyk mcp` with the server's default transport, which is not stdio — an installed tile
  /// that could never connect.
  func testRegistryReplaysNamedArgumentsThatCarryALiteralValue() throws {
    let payload = """
      {"servers": [{"server": {"name": "io.snyk/mcp", "description": "d", "packages": [
        {"registryType": "npm", "identifier": "snyk", "version": "1.1299.1",
         "transport": {"type": "stdio"},
         "packageArguments": [{"value": "mcp", "type": "positional"},
                              {"value": "stdio", "type": "named", "name": "-t"},
                              {"type": "named", "name": "--project-ref"}]}]}}]}
      """
    XCTAssertEqual(
      ExtensionCatalog.mcpEntries(fromRegistry: Data(payload.utf8)).first?.install,
      .mcpStdio(command: "npx", args: ["snyk@1.1299.1", "mcp", "-t", "stdio"], requiredEnv: []),
      "a named argument with no value needs input we cannot supply and stays out")
  }

  /// `ai.smithery/*` republishes other people's servers behind a Smithery-hosted endpoint and a
  /// second consent screen. Listing them puts a broker between the user and a server they can
  /// install straight from its publisher.
  func testRegistryDropsRepublishedNamespaces() throws {
    let payload = """
      {"servers": [
        {"server": {"name": "ai.smithery/acme-thing", "description": "d",
                    "remotes": [{"type": "streamable-http", "url": "https://server.smithery.ai/x"}]}},
        {"server": {"name": "com.acme/mcp", "description": "d",
                    "remotes": [{"type": "streamable-http", "url": "https://mcp.acme.com"}]}}
      ]}
      """
    XCTAssertEqual(
      ExtensionCatalog.mcpEntries(fromRegistry: Data(payload.utf8)).map(\.id), ["com.acme/mcp"])
  }

  /// A registry namespace is DNS-verified, but `io.github.<user>` only proves someone holds a
  /// GitHub account. Searching "gmail" returns dozens of those ahead of the brands alphabetically.
  func testSearchResultsRankVerifiedBrandsAbovePersonalNamespaces() throws {
    let payload = """
      {"servers": [
        {"server": {"name": "io.github.someone/gmail", "description": "d",
                    "remotes": [{"type": "streamable-http", "url": "https://a.example"}]}},
        {"server": {"name": "com.zapier/mcp", "description": "d",
                    "remotes": [{"type": "streamable-http", "url": "https://b.example"}]}},
        {"server": {"name": "io.github.other/gmail", "description": "d",
                    "remotes": [{"type": "streamable-http", "url": "https://c.example"}]}},
        {"server": {"name": "app.linear/linear", "description": "d",
                    "remotes": [{"type": "streamable-http", "url": "https://d.example"}]}}
      ]}
      """
    XCTAssertEqual(
      ExtensionCatalog.mcpEntries(fromRegistry: Data(payload.utf8)).map(\.id),
      ["com.zapier/mcp", "app.linear/linear", "io.github.someone/gmail", "io.github.other/gmail"],
      "registry order must be preserved within each group")
  }

  func testMalformedRegistryPayloadYieldsNoEntries() throws {
    XCTAssertTrue(ExtensionCatalog.mcpEntries(fromRegistry: Data("not json".utf8)).isEmpty)
    XCTAssertTrue(ExtensionCatalog.mcpEntries(fromRegistry: Data(#"{"servers": 3}"#.utf8)).isEmpty)
  }

  /// A pasted key is just the key; an Authorization header needs its scheme, or the server sees a
  /// malformed header and reports the request as unauthenticated.
  func testAuthorizationHeaderGainsItsSchemeButOthersAreLeftAlone() throws {
    XCTAssertEqual(
      ExtensionCatalogService.authorizationValue(header: "Authorization", secret: "abc123"),
      "Bearer abc123")
    XCTAssertEqual(
      ExtensionCatalogService.authorizationValue(header: "authorization", secret: "Bearer abc123"),
      "Bearer abc123", "a key that already carries a scheme must not be double-prefixed")
    XCTAssertEqual(
      ExtensionCatalogService.authorizationValue(header: "X-Api-Key", secret: "abc123"), "abc123")
  }

  // MARK: - Skills index

  /// A skill is a folder. 22 of the 33 skills in the two default catalogs ship files their
  /// SKILL.md points at — `docx` alone carries 59, including the scripts it tells the model to
  /// run — so installing the Markdown alone yields instructions that reference nothing.
  func testSkillsRepoTreeCarriesTheWholeFolder() throws {
    let payload = """
      {"tree": [
        {"type": "blob", "path": "README.md"},
        {"type": "blob", "path": "skills/web-research/SKILL.md"},
        {"type": "blob", "path": "skills/web-research/scripts/fetch.py"},
        {"type": "blob", "path": "skills/web-research/references/sources.md"},
        {"type": "tree", "path": "skills/web-research/scripts"},
        {"type": "blob", "path": "skills/pdf/SKILL.md"},
        {"type": "blob", "path": "skills/no-manifest/notes.md"}
      ]}
      """
    let entries = ExtensionCatalog.skillEntries(
      fromRepoTree: Data(payload.utf8), repo: "acme/skills", ref: "main")

    XCTAssertEqual(
      entries.map(\.name), ["Web Research", "Pdf"],
      "a folder with no SKILL.md is not a skill")
    XCTAssertEqual(
      entries[0].install,
      .skill(
        source: ExtensionCatalog.SkillSource(
          repo: "acme/skills", ref: "main", slug: "web-research",
          files: ["SKILL.md", "references/sources.md", "scripts/fetch.py"])),
      "SKILL.md leads: it is fetched and checked before anything is written")
    XCTAssertEqual(
      entries[0].install.needsInput, false, "a skill install never prompts for a secret")
  }

  /// The file list is remote input that decides where bytes land under ~/.omi.
  func testSkillPathsThatEscapeTheFolderAreRejected() throws {
    let source = ExtensionCatalog.SkillSource(
      repo: "acme/skills", ref: "main", slug: "x", files: ["SKILL.md"])
    for path in ["../evil", "a/../../evil", "/etc/passwd", "", "a//b", "./x"] {
      XCTAssertFalse(ExtensionCatalog.SkillSource.isSafe(path: path), path)
      XCTAssertNil(source.rawURL(for: path), path)
    }
    XCTAssertEqual(
      source.rawURL(for: "scripts/run.py")?.absoluteString,
      "https://raw.githubusercontent.com/acme/skills/main/skills/x/scripts/run.py")

    let payload = """
      {"tree": [{"type": "blob", "path": "skills/x/SKILL.md"},
                {"type": "blob", "path": "skills/x/../../escape.sh"}]}
      """
    guard
      case .skill(let parsed) = try XCTUnwrap(
        ExtensionCatalog.skillEntries(fromRepoTree: Data(payload.utf8), repo: "a/b", ref: "main")
          .first
      ).install
    else { return XCTFail("expected a skill install") }
    XCTAssertEqual(parsed.files, ["SKILL.md"])
  }

  /// Real SKILL.md files in the wild use YAML block scalars for long descriptions. Reading only the
  /// value on the `description:` line showed the user a lone ">" on those cards.
  func testSkillDescriptionReadsBlockScalarsAndPlainValues() throws {
    let plain = "---\nname: x\ndescription: Use when asked to do the thing.\n---\n\nBody."
    XCTAssertEqual(
      ExtensionCatalog.skillDescription(fromMarkdown: plain), "Use when asked to do the thing.")

    let quoted = "---\ndescription: \"Quoted value\"\n---\n\nBody."
    XCTAssertEqual(ExtensionCatalog.skillDescription(fromMarkdown: quoted), "Quoted value")

    let folded = """
      ---
      name: x
      description: >
        Creating algorithmic art using p5.js
        with seeded randomness.
      license: MIT
      ---

      Body.
      """
    XCTAssertEqual(
      ExtensionCatalog.skillDescription(fromMarkdown: folded),
      "Creating algorithmic art using p5.js with seeded randomness.")

    let literal = "---\ndescription: |-\n  First line.\n  Second line.\n---\n\nBody."
    XCTAssertEqual(
      ExtensionCatalog.skillDescription(fromMarkdown: literal), "First line. Second line.")

    XCTAssertNil(ExtensionCatalog.skillDescription(fromMarkdown: "# No frontmatter\n\nBody."))
    XCTAssertNil(ExtensionCatalog.skillDescription(fromMarkdown: "---\nname: x\n---\n\nBody."))
  }

  // MARK: - Sources

  private func defaults(for kind: ExtensionCatalog.Kind) -> [ExtensionCatalog.Source] {
    ExtensionCatalog.defaultSources.filter { $0.kind == kind }
  }

  func testSourcesFallBackToDefaultsWhenConfigIsAbsentOrUnusable() throws {
    let missing = tempRoot.appendingPathComponent("nope.json")
    XCTAssertEqual(ExtensionCatalog.sources(kind: .mcp, configURL: missing), defaults(for: .mcp))

    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    let broken = tempRoot.appendingPathComponent("catalogs.json")
    try Data("{ not json".utf8).write(to: broken)
    XCTAssertEqual(ExtensionCatalog.sources(kind: .skill, configURL: broken), defaults(for: .skill))
  }

  /// The official registry is the only MCP marketplace shipped by default: it is the one index
  /// whose namespaces are DNS-verified against the publisher's own domain.
  func testMcpDefaultsAreTheOfficialRegistryOnly() throws {
    let feeds = defaults(for: .mcp).map(\.feed)
    XCTAssertEqual(feeds.count, 1)
    XCTAssertTrue(feeds.contains { if case .mcpRegistry = $0 { return true } else { return false } })
  }

  /// A file that configures one kind must not silently delete the other kind's marketplace.
  func testConfiguringOneKindLeavesTheOtherOnItsDefault() throws {
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    let config = tempRoot.appendingPathComponent("catalogs.json")
    try Data(
      #"{"catalogs": [{"kind": "skill", "type": "github-skills", "repo": "acme/s", "ref": "dev"}]}"#
        .utf8
    ).write(to: config)

    XCTAssertEqual(
      ExtensionCatalog.sources(kind: .skill, configURL: config),
      [ExtensionCatalog.Source(kind: .skill, feed: .githubSkillsRepo(repo: "acme/s", ref: "dev"))])
    XCTAssertEqual(ExtensionCatalog.sources(kind: .mcp, configURL: config), defaults(for: .mcp))
  }

  // MARK: - Logos

  /// Every icon source must be one the publisher controls. A guessed or third-party URL either
  /// renders a broken tile or tells someone else which servers this user is browsing.
  func testIconPrefersDeclaredIconThenRepoOwnerThenFavicon() throws {
    let declared: [String: Any] = [
      "icons": [["src": "https://cdn.example.com/logo.png"]],
      "repository": ["url": "https://github.com/acme/thing"],
    ]
    XCTAssertEqual(
      ExtensionCatalog.iconURL(for: declared, websiteURL: "https://acme.com"),
      "https://cdn.example.com/logo.png")

    let repoOnly: [String: Any] = ["repository": ["url": "https://github.com/acme/thing"]]
    XCTAssertEqual(
      ExtensionCatalog.iconURL(for: repoOnly, websiteURL: "https://acme.com"),
      "https://github.com/acme.png?size=128")

    XCTAssertEqual(
      ExtensionCatalog.iconURL(for: [:], websiteURL: "https://acme.com/docs/mcp"),
      "https://acme.com/favicon.ico")

    XCTAssertEqual(ExtensionCatalog.iconURL(for: [:], websiteURL: nil), "")
  }

  /// An http icon is not rendered: the spec requires HTTPS, and a mixed-content tile is a
  /// downgrade the user never asked for.
  func testInsecureDeclaredIconIsIgnored() throws {
    let insecure: [String: Any] = ["icons": [["src": "http://cdn.example.com/logo.png"]]]
    XCTAssertEqual(ExtensionCatalog.iconURL(for: insecure, websiteURL: nil), "")
  }

  func testGitHubOwnerIsOnlyTakenFromGitHubURLs() throws {
    XCTAssertEqual(ExtensionCatalog.gitHubOwner(fromRepositoryURL: "https://github.com/acme/x"), "acme")
    XCTAssertNil(ExtensionCatalog.gitHubOwner(fromRepositoryURL: "https://gitlab.com/acme/x"))
    XCTAssertNil(ExtensionCatalog.gitHubOwner(fromRepositoryURL: "https://github.com"))
  }

  // MARK: - Featured servers

  /// Featured entries are fetched one server at a time, and the curated title wins over whatever
  /// the registry happens to carry — most first-party entries publish no title at all.
  func testFeaturedEntryUsesLatestVersionAndCuratedTitle() throws {
    let payload = """
      {"servers": [
        {"server": {"name": "com.acme/mcp", "description": "old",
                    "remotes": [{"type": "streamable-http", "url": "https://a.acme.com/mcp"}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": false}}},
        {"server": {"name": "com.acme/mcp", "description": "new", "websiteUrl": "https://acme.com",
                    "remotes": [{"type": "streamable-http", "url": "https://b.acme.com/mcp"}]},
         "_meta": {"io.modelcontextprotocol.registry/official": {"isLatest": true}}}
      ]}
      """
    let entry = try XCTUnwrap(
      ExtensionCatalog.mcpEntry(fromVersions: Data(payload.utf8), name: "com.acme/mcp", title: "Acme"))

    XCTAssertEqual(entry.name, "Acme")
    XCTAssertEqual(entry.detail, "new")
    XCTAssertEqual(entry.publisher, "com.acme")
    XCTAssertEqual(entry.iconURL, "https://acme.com/favicon.ico")
    XCTAssertEqual(
      entry.install, .mcpRemote(url: "https://b.acme.com/mcp", transport: "http", secretHeader: nil))
  }

  func testFeaturedListIsUniqueAndFullyQualified() throws {
    let names = ExtensionCatalog.featuredMcpServers.map(\.name)
    XCTAssertEqual(Set(names).count, names.count, "a duplicate would render the same tile twice")
    for name in names {
      XCTAssertTrue(name.contains("/"), "\(name) is not a registry-qualified server name")
      XCTAssertFalse(
        name.hasPrefix("io.github."),
        "\(name) is a personal GitHub namespace, not a brand's verified domain")
    }
  }

  func testVersionsURLEscapesTheSlashInAServerName() throws {
    let base = try XCTUnwrap(URL(string: "https://registry.example.io"))
    let url = try XCTUnwrap(
      ExtensionCatalogService.versionsURL(base: base, serverName: "com.acme/mcp"))
    XCTAssertEqual(url.absoluteString, "https://registry.example.io/v0/servers/com.acme%2Fmcp/versions")
  }

  // MARK: - OAuth discovery

  /// RFC 8414 inserts the well-known segment *before* an issuer's path, not after it. Hosted
  /// providers issue per-server paths (`https://auth.example/brave`), so appending would probe
  /// `/brave/.well-known/...` — a 404 — and the server would look like it had no OAuth at all.
  func testIssuerWellKnownInsertsTheSegmentBeforeAnIssuerPath() throws {
    let scoped = try XCTUnwrap(URL(string: "https://auth.example.ai/brave"))
    XCTAssertEqual(
      LocalMcpStore.issuerWellKnown(issuer: scoped, suffix: "oauth-authorization-server")?
        .absoluteString,
      "https://auth.example.ai/.well-known/oauth-authorization-server/brave")

    let bare = try XCTUnwrap(URL(string: "https://auth.example.ai"))
    XCTAssertEqual(
      LocalMcpStore.issuerWellKnown(issuer: bare, suffix: "openid-configuration")?.absoluteString,
      "https://auth.example.ai/.well-known/openid-configuration")
  }

  /// Discovery starts from the resource's origin, so a server URL carrying a path or port must not
  /// send the probe to the wrong place.
  func testOriginDropsPathButKeepsPort() throws {
    XCTAssertEqual(
      LocalMcpStore.origin(of: try XCTUnwrap(URL(string: "https://x.example/mcp/v1")))?
        .absoluteString, "https://x.example")
    XCTAssertEqual(
      LocalMcpStore.origin(of: try XCTUnwrap(URL(string: "http://127.0.0.1:8080/mcp")))?
        .absoluteString, "http://127.0.0.1:8080")
  }

  // MARK: - Imported skill validation

  /// A README dropped on the editor is not a skill. Without a description the model has nothing to
  /// match a request against, so it would install as a skill that can never be selected.
  func testImportedMarkdownMustCarrySkillFrontmatter() throws {
    XCTAssertNotNil(
      LocalSkillsStore.validationError(forImportedMarkdown: "# Just a readme\n\nSome notes."))
    XCTAssertNotNil(
      LocalSkillsStore.validationError(forImportedMarkdown: "---\nname: x\n---\n\nBody."))
    XCTAssertNotNil(
      LocalSkillsStore.validationError(
        forImportedMarkdown: "---\nname: x\ndescription: use when asked\n---\n\n   "))
    XCTAssertNil(
      LocalSkillsStore.validationError(
        forImportedMarkdown: "---\nname: x\ndescription: use when asked\n---\n\nDo the thing."))
  }

  /// A feed is resolved by type, never by position — the featured list looks up the registry feed
  /// among however many mirrors an org has configured, in whatever order it wrote them.
  func testFeedLookupDoesNotDependOnSourceOrder() throws {
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    let config = tempRoot.appendingPathComponent("catalogs.json")
    try Data(
      #"""
      {"catalogs": [
        {"kind": "skill", "type": "github-skills", "repo": "acme/s", "ref": "main"},
        {"kind": "mcp", "type": "mcp-registry", "url": "https://registry.example"}
      ]}
      """#.utf8
    ).write(to: config)

    let feeds = ExtensionCatalog.sources(kind: .mcp, configURL: config).map(\.feed)
    XCTAssertEqual(
      feeds, [.mcpRegistry(baseURL: try XCTUnwrap(URL(string: "https://registry.example")))])
  }

  /// An unknown catalog type is dropped, not treated as a parse failure that would silently swap
  /// the whole file for the defaults.
  func testUnknownCatalogTypeIsDropped() throws {
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    let config = tempRoot.appendingPathComponent("catalogs.json")
    try Data(
      #"""
      {"catalogs": [
        {"kind": "mcp", "type": "smithery", "url": "https://registry.smithery.ai"},
        {"kind": "mcp", "type": "mcp-registry", "url": "https://registry.example"}
      ]}
      """#.utf8
    ).write(to: config)

    let feeds = ExtensionCatalog.sources(kind: .mcp, configURL: config).map(\.feed)
    XCTAssertEqual(
      feeds, [.mcpRegistry(baseURL: try XCTUnwrap(URL(string: "https://registry.example")))])
  }

  // MARK: - Install naming

  /// Installing must never overwrite a server the user configured by hand under the same name.
  func testInstallNameAvoidsCollisionWithAnExistingServer() throws {
    XCTAssertEqual(ExtensionCatalogService.availableServerName(for: "GitHub", taken: []), "github")
    XCTAssertEqual(
      ExtensionCatalogService.availableServerName(for: "GitHub", taken: ["github"]), "github-2")
    XCTAssertEqual(
      ExtensionCatalogService.availableServerName(for: "GitHub", taken: ["github", "github-2"]),
      "github-3")
    XCTAssertEqual(ExtensionCatalogService.availableServerName(for: "!!!", taken: []), "server")
  }

  func testRegistryURLCarriesLatestVersionAndSearch() throws {
    let base = try XCTUnwrap(URL(string: "https://registry.example.io"))
    let url = try XCTUnwrap(ExtensionCatalogService.registryURL(base: base, search: " playwright "))
    XCTAssertEqual(url.path, "/v0/servers")
    let query = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
    XCTAssertEqual(query.first { $0.name == "version" }?.value, "latest")
    XCTAssertEqual(query.first { $0.name == "search" }?.value, "playwright")

    let blank = try XCTUnwrap(ExtensionCatalogService.registryURL(base: base, search: "   "))
    let blankQuery = URLComponents(url: blank, resolvingAgainstBaseURL: false)?.queryItems ?? []
    XCTAssertNil(blankQuery.first { $0.name == "search" })
  }
}
