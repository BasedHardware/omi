import AppKit
import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

// MARK: - MCP Servers section

/// User-added MCP servers from ~/.omi/mcp.json, listed on the Apps page next
/// to Imports/Exports.
struct McpServersSection: View {
  @ObservedObject var appProvider: AppProvider
  var searchText: String = ""
  let onAdd: () -> Void
  let onSelectLocal: (LocalMcpStore.Entry) -> Void
  let onSelectCatalogEntry: (ExtensionCatalog.Entry) -> Void

  private var servers: [LocalMcpStore.Entry] {
    appProvider.localMcpServers.filter { matchesSearch($0.name, $0.summary, query: searchText) }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text("MCP Servers")
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text("Connect remote MCP servers or local commands; their tools become available in chat")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        Spacer()
        Button(action: onAdd) {
          ConnectionModalActionButton(title: "Add Server")
        }
        .buttonStyle(.plain)
      }

      if servers.isEmpty {
        AgentExtensionEmptyCard(
          icon: "server.rack",
          text: searchText.isEmpty
            ? "No servers yet. Add a remote URL, or a local command like npx @playwright/mcp@latest."
            : "No installed server matches \(searchText).")
      } else {
        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 260), spacing: OmiSpacing.md)],
          alignment: .leading,
          spacing: OmiSpacing.md
        ) {
          ForEach(servers) { server in
            let status = appProvider.mcpStatuses[server.name] ?? .checking
            AgentExtensionCard(
              icon: server.isCommand ? "terminal" : "server.rack",
              imageUrl: "",
              title: server.name,
              subtitle: server.isCommand ? "Local command" : "Remote",
              detail: status.detail ?? server.summary,
              statusText: status.label,
              statusActive: status.isHealthy,
              actionTitle: status == .needsAuth ? "Sign In" : "Manage",
              actionIsSecondary: status != .needsAuth
            ) {
              onSelectLocal(server)
            }
          }
        }
      }

      ExtensionMarketplaceSection(
        entries: marketplaceEntries,
        isLoading: appProvider.isLoadingMcpCatalog,
        loadingText: "Loading the MCP registry…",
        icon: { $0.subtitle == "Remote" ? "server.rack" : "terminal" },
        onSelect: onSelectCatalogEntry
      )
    }
    .task(id: searchText) {
      await ExtensionMarketplaceSection.debounce()
      guard !Task.isCancelled else { return }
      await appProvider.fetchMcpCatalog(search: searchText)
    }
    .task(id: appProvider.localMcpServers.map(\.name)) {
      // The file is hand-editable by design and nothing watches it; each visit
      // here stats it once and notifies the runtime when it moved under us.
      if LocalMcpStore.checkForExternalChanges() {
        await appProvider.fetchUserExtensions()
      }
      await appProvider.refreshMcpStatuses()
    }
  }

  /// A catalog entry whose local name is already taken is not offered again: installing it would
  /// write a suffixed duplicate, which reads as a second copy rather than an upgrade.
  private var marketplaceEntries: [ExtensionCatalog.Entry] {
    let taken = Set(appProvider.localMcpServers.map(\.name))
    return appProvider.mcpCatalog.filter { !taken.contains(LocalSkillsStore.slugify($0.name)) }
  }
}

// MARK: - Skills section

/// User-authored skills (SKILL.md in ~/.omi/skills), listed on the Apps page.
struct SkillsSection: View {
  @ObservedObject var appProvider: AppProvider
  var searchText: String = ""
  let onAdd: () -> Void
  let onSelect: (LocalSkillsStore.Skill) -> Void
  let onSelectCatalogEntry: (ExtensionCatalog.Entry) -> Void

  private var skills: [LocalSkillsStore.Skill] {
    appProvider.localSkills.filter { matchesSearch($0.name, $0.description, query: searchText) }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text("Skills")
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text("Teach the assistant reusable instructions it loads when relevant")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        Spacer()
        Button(action: onAdd) {
          ConnectionModalActionButton(title: "Add Skill")
        }
        .buttonStyle(.plain)
      }

      if skills.isEmpty {
        AgentExtensionEmptyCard(
          icon: "graduationcap",
          text: searchText.isEmpty
            ? "No skills yet. Paste or drop a SKILL.md, or write one from scratch."
            : "No installed skill matches \(searchText).")
      } else {
        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 260), spacing: OmiSpacing.md)],
          alignment: .leading,
          spacing: OmiSpacing.md
        ) {
          ForEach(skills) { skill in
            AgentExtensionCard(
              icon: "graduationcap",
              imageUrl: "",
              title: skill.name,
              subtitle: "",
              detail: skill.description,
              statusText: "Active in chat",
              statusActive: true
            ) {
              onSelect(skill)
            }
          }
        }
      }

      ExtensionMarketplaceSection(
        entries: marketplaceEntries,
        isLoading: appProvider.isLoadingSkillCatalog,
        loadingText: "Loading skills…",
        icon: { _ in "graduationcap" },
        onSelect: onSelectCatalogEntry
      )
    }
    .task(id: searchText) {
      await ExtensionMarketplaceSection.debounce()
      guard !Task.isCancelled else { return }
      await appProvider.fetchSkillCatalog(search: searchText)
    }
  }

  private var marketplaceEntries: [ExtensionCatalog.Entry] {
    let taken = Set(appProvider.localSkills.map(\.slug))
    return appProvider.skillCatalog.filter { !taken.contains(LocalSkillsStore.slugify($0.name)) }
  }
}

/// The page's one search field covers whichever section is showing, so both sections narrow on
/// the same query rather than leaving it inert over their lists.
private func matchesSearch(_ fields: String..., query: String) -> Bool {
  let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
  guard !trimmed.isEmpty else { return true }
  return fields.contains { $0.localizedCaseInsensitiveContains(trimmed) }
}

// MARK: - Marketplace

/// The "Marketplace" block both extension sections end with: browsable entries from a catalog,
/// in the same card grid as the installed ones above.
///
/// It renders nothing at all when the catalog is empty — an unreachable registry then costs the
/// user a section they were not using rather than an error over the servers they installed.
struct ExtensionMarketplaceSection: View {
  let entries: [ExtensionCatalog.Entry]
  let isLoading: Bool
  let loadingText: String
  let icon: (ExtensionCatalog.Entry) -> String
  let onSelect: (ExtensionCatalog.Entry) -> Void

  /// Typing must not fire one registry request per keystroke; a cancelled task skips the fetch.
  static func debounce() async {
    try? await Task.sleep(nanoseconds: 350_000_000)
  }

  var body: some View {
    if isLoading && entries.isEmpty {
      AgentExtensionEmptyCard(icon: "bag", text: loadingText)
    } else if !entries.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        Text("Marketplace")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)

        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 260), spacing: OmiSpacing.md)],
          alignment: .leading,
          spacing: OmiSpacing.md
        ) {
          ForEach(entries) { entry in
            AgentExtensionCard(
              icon: icon(entry),
              imageUrl: entry.iconURL,
              title: entry.name,
              subtitle: entry.subtitle,
              detail: entry.detail,
              statusText: entry.install.needsInput ? "Needs a key" : entry.publisher,
              statusActive: false,
              actionTitle: "View",
              actionIsSecondary: true
            ) {
              // A card press opens the detail sheet. Installing writes an executable command or a
              // credentialed endpoint into ~/.omi, so it happens only from a screen that has shown
              // the user exactly what will be written.
              onSelect(entry)
            }
          }
        }
      }
    }
  }
}

/// What a marketplace entry is and exactly what installing it writes, so the decision to run a
/// third party's command — or hand it a credential — is made against the facts, not a card.
struct ExtensionDetailSheet: View {
  let entry: ExtensionCatalog.Entry
  @ObservedObject var appProvider: AppProvider
  let onDismiss: () -> Void

  @State private var values: [String: String] = [:]
  @State private var errorText: String?
  @State private var isInstalling = false

  private var requiredFields: [String] {
    switch entry.install {
    case .mcpRemote(_, _, let header): return header.map { [$0] } ?? []
    case .mcpStdio(_, _, let env): return env
    case .skill: return []
    }
  }

  /// The literal thing that lands in ~/.omi. Shown verbatim: a command a user cannot see is a
  /// command they cannot refuse.
  private var installSummary: String {
    switch entry.install {
    case .mcpRemote(let url, let transport, _): return "\(transport.uppercased())  \(url)"
    case .mcpStdio(let command, let args, _): return ([command] + args).joined(separator: " ")
    case .skill(let source):
      let folder = "\(source.repo)/skills/\(source.slug)"
      guard source.files.count > 1 else { return "\(folder)  ·  SKILL.md" }
      return "\(folder)  ·  SKILL.md and \(source.files.count - 1) bundled files"
    }
  }

  private var installSummaryLabel: String {
    if case .skill = entry.install { return "Source" }
    if case .mcpStdio = entry.install { return "Runs on your Mac" }
    return "Endpoint"
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.md) {
        ExtensionLogo(imageUrl: entry.iconURL, fallbackSymbol: fallbackSymbol, size: 44)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(entry.name)
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text(entry.publisher.isEmpty ? entry.subtitle : "\(entry.subtitle) · \(entry.publisher)")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(1)
        }
        Spacer()
      }

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          if !entry.detail.isEmpty {
            Text(entry.detail)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }

          labelled(installSummaryLabel) {
            Text(installSummary)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.primary)
              .textSelection(.enabled)
              .fixedSize(horizontal: false, vertical: true)
          }

          ForEach(requiredFields, id: \.self) { field in
            labelled(field) {
              SecureField("Required", text: binding(for: field))
                .textFieldStyle(.roundedBorder)
            }
          }

          if let website = entry.websiteURL, let url = URL(string: website) {
            Link("Open publisher page", destination: url)
              .scaledFont(size: OmiType.caption)
          }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }

      if let errorText {
        Text(errorText)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.errorRed)
          .fixedSize(horizontal: false, vertical: true)
      }

      HStack {
        Spacer()
        Button("Cancel", action: onDismiss)
          .buttonStyle(.plain)
          .foregroundColor(Ink.secondary)
        Button(action: install) {
          ConnectionModalActionButton(title: isInstalling ? "Installing…" : "Install")
        }
        .buttonStyle(.plain)
        .disabled(isInstalling)
      }
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
  }

  private var fallbackSymbol: String {
    switch entry.install {
    case .skill: return "graduationcap"
    case .mcpStdio: return "terminal"
    case .mcpRemote: return "server.rack"
    }
  }

  @ViewBuilder
  private func labelled<Content: View>(_ label: String, @ViewBuilder content: () -> Content)
    -> some View
  {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
      content()
    }
  }

  private func binding(for field: String) -> Binding<String> {
    Binding(get: { values[field] ?? "" }, set: { values[field] = $0 })
  }

  private func install() {
    isInstalling = true
    errorText = nil
    Task {
      do {
        try await ExtensionCatalogService.install(entry, secrets: values)
        await appProvider.fetchUserExtensions()
        onDismiss()
      } catch {
        errorText = error.localizedDescription
        isInstalling = false
      }
    }
  }
}

/// A publisher logo that degrades to a symbol.
///
/// `AsyncImage` is not usable here: many publishers serve SVG, which SwiftUI's image decoder
/// rejects while `NSImage` renders it, so half the marketplace showed a fallback symbol beside the
/// half that did not. Remote art is decoration either way — a slow, missing, or undecodable image
/// leaves the symbol rather than a hole where a card's identity should be.
struct ExtensionLogo: View {
  let imageUrl: String
  let fallbackSymbol: String
  var size: CGFloat = 40

  @State private var image: NSImage?

  var body: some View {
    Group {
      if let image {
        Image(nsImage: image).resizable().aspectRatio(contentMode: .fit).padding(size * 0.12)
      } else {
        symbol
      }
    }
    .frame(width: size, height: size)
    .background(Ink.wash)
    .cornerRadius(OmiChrome.smallControlRadius)
    // The loader hands back bytes, not an NSImage: decoded images are not Sendable, so
    // returning one across the actor boundary is a strict-concurrency error. Decoding here
    // also keeps every NSImage on the main actor, which is where it is drawn.
    .task(id: imageUrl) {
      image = await ExtensionLogoLoader.shared.data(for: imageUrl).flatMap(NSImage.init(data:))
    }
  }

  private var symbol: some View {
    Image(systemName: fallbackSymbol)
      .scaledFont(size: OmiType.subheading)
      .foregroundColor(Ink.primary)
  }
}

/// Session cache for catalog logo *bytes*. The same publisher icon appears on a card and again in
/// the detail sheet, and the grid re-renders on every keystroke of the search field.
///
/// Bytes rather than images: `NSImage` is not Sendable, so handing one out of an actor is a
/// strict-concurrency error, and a decoded image is not safe to share across isolation domains
/// anyway. Callers decode on their own actor.
actor ExtensionLogoLoader {
  static let shared = ExtensionLogoLoader()

  /// Enough for every tile of a catalog page and its detail sheets. A miss costs one request,
  /// so the cap trades a rare refetch for a bound that a long browsing session cannot exceed.
  private static let capacity = 128
  private static let maxBytes = 2 * 1024 * 1024

  /// `nil` value means "fetched and unusable" — cached so a broken icon is not retried per render.
  private var cache: [String: Data?] = [:]
  /// Insertion order, oldest first, for eviction.
  private var order: [String] = []

  func data(for urlString: String) async -> Data? {
    if let cached = cache[urlString] { return cached }
    let loaded = await Self.fetch(urlString)
    if cache.updateValue(loaded, forKey: urlString) == nil { order.append(urlString) }
    while order.count > Self.capacity {
      cache.removeValue(forKey: order.removeFirst())
    }
    return loaded
  }

  private static func fetch(_ urlString: String) async -> Data? {
    guard let url = URL(string: urlString), url.scheme == "https" else { return nil }
    var request = URLRequest(url: url, timeoutInterval: 10)
    request.setValue("image/*", forHTTPHeaderField: "Accept")
    guard let (data, response) = try? await URLSession.shared.data(for: request),
      (response as? HTTPURLResponse).map({ (200..<300).contains($0.statusCode) }) == true,
      data.count <= maxBytes
    else { return nil }
    return data
  }
}

// MARK: - Shared section pieces

struct AgentExtensionEmptyCard: View {
  let icon: String
  let text: String

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.title)
        .foregroundColor(Ink.secondary)
      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.leading)
      Spacer()
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .cornerRadius(OmiChrome.smallControlRadius)
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .stroke(Ink.separator, lineWidth: 1)
    )
  }
}

struct AgentExtensionCard: View {
  let icon: String
  let imageUrl: String
  let title: String
  let subtitle: String
  let detail: String
  let statusText: String
  let statusActive: Bool
  /// Trailing button label. Installed cards manage; marketplace cards install.
  var actionTitle: String = "Manage"
  var actionIsSecondary: Bool = true
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.md) {
          iconView

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text(title)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)
              .lineLimit(1)

            if !subtitle.isEmpty {
              Text(subtitle)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
                .lineLimit(1)
            }
          }

          Spacer()
        }

        Text(detail)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .lineLimit(2)
          .multilineTextAlignment(.leading)
          .frame(maxWidth: .infinity, minHeight: 28, alignment: .topLeading)

        HStack {
          Text(statusText)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(statusActive ? Ink.primary : Ink.secondary)

          Spacer()

          ImportConnectorActionButton(title: actionTitle, isConnected: actionIsSecondary)
        }
      }
      .padding(OmiSpacing.md)
      .background(isHovering ? Ink.rowFillHover : Ink.rowFill)
      .cornerRadius(OmiChrome.smallControlRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .stroke(Ink.separator, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }

  @ViewBuilder private var iconView: some View {
    ExtensionLogo(imageUrl: imageUrl, fallbackSymbol: icon)
  }
}

// MARK: - Add MCP Server sheet

struct AddMcpServerSheet: View {
  @ObservedObject var appProvider: AppProvider
  let onDismiss: () -> Void

  private enum Phase: Equatable {
    case editing
    case submitting
    case waitingForAuth
    case savedLocal
  }

  private enum Mode: String, CaseIterable, Identifiable {
    case remote = "Remote URL"
    case local = "Local Command"

    var id: String { rawValue }

    var icon: String { self == .remote ? "server.rack" : "terminal" }

    var automationID: String { self == .remote ? "remote" : "local" }
  }

  private enum Field: Hashable {
    case name, url, key, command
  }

  @State private var name = ""
  @State private var serverUrl = ""
  @State private var apiKey = ""
  @State private var commandLine = ""
  @State private var mode: Mode = .remote
  @State private var phase: Phase = .editing
  @State private var errorMessage: String?
  @FocusState private var focusedField: Field?

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xl) {
      header

      switch phase {
      case .savedLocal:
        savedLocalContent
      case .waitingForAuth:
        waitingContent
      default:
        formContent
      }

      // The overlay sizes itself to the tallest lane; without this the shorter ones float
      // vertically centred in a box that is not theirs.
      Spacer(minLength: 0)
    }
    .padding(OmiSpacing.xxl)
    // The title needs more room above it than beside it, or it reads as pinned to the card's edge.
    .padding(.top, OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .topLeading)
    .background(Ink.surface)
  }

  private var header: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Image(systemName: mode.icon)
        .scaledFont(size: OmiType.subheading, weight: .medium)
        .foregroundColor(Ink.primary)
        .frame(width: 40, height: 40)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
            .fill(Ink.rowFill)
        )
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
            .strokeBorder(Ink.separator, lineWidth: 1)
        )
        .omiAnimation(.easeOut(duration: 0.15), value: mode)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text("Add MCP Server")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text("Its tools become available to the assistant in chat")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: OmiSpacing.md)

      DismissButton(action: onDismiss)
    }
  }

  private var formContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      modeChips

      labeledField("Name", field: .name) {
        TextField(mode == .remote ? "e.g. Linear" : "e.g. Playwright", text: $name)
      }
      .accessibilityIdentifier("add-mcp-name")

      if mode == .remote {
        labeledField("Server URL", field: .url) {
          TextField("https://mcp.example.com/mcp", text: $serverUrl)
        }
        .accessibilityIdentifier("add-mcp-url")
        labeledField("API key", field: .key, hint: "Leave empty for public or OAuth servers") {
          SecureField("", text: $apiKey)
        }
        .accessibilityIdentifier("add-mcp-api-key")
      } else {
        labeledField(
          "Command", field: .command,
          hint: "Runs on your Mac and is saved to ~/.omi/mcp.json."
        ) {
          TextField("npx @playwright/mcp@latest", text: $commandLine)
        }
        .accessibilityIdentifier("add-mcp-command")
      }

      errorRow

      footer
    }
  }

  private var modeChips: some View {
    HStack(spacing: OmiSpacing.xs) {
      ForEach(Mode.allCases) { candidate in
        Button {
          errorMessage = nil
          OmiMotion.withGated(.easeOut(duration: 0.15)) { mode = candidate }
        } label: {
          HStack(spacing: OmiSpacing.xs) {
            Image(systemName: candidate.icon)
              .scaledFont(size: OmiType.caption)
            Text(candidate.rawValue)
              .scaledFont(size: OmiType.caption, weight: mode == candidate ? .semibold : .regular)
          }
          .foregroundStyle(GlassShell.controlLabel(isProminent: mode == candidate))
          .padding(.horizontal, OmiSpacing.lg)
          .padding(.vertical, OmiSpacing.sm)
          .glassChip(isActive: mode == candidate)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("add-mcp-mode-\(candidate.automationID)")
        .accessibilityAddTraits(mode == candidate ? .isSelected : [])
      }
    }
  }

  private var footer: some View {
    HStack(spacing: OmiSpacing.lg) {
      Spacer()

      Button("Cancel", action: onDismiss)
        .buttonStyle(.plain)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)

      Button {
        Task { await submit() }
      } label: {
        ConnectionModalActionButton(title: phase == .submitting ? "Connecting…" : "Connect")
          // The primitive has no disabled state of its own, and a live-looking button that does
          // nothing is worse than a dim one.
          .opacity(canSubmit && phase != .submitting ? 1 : 0.45)
      }
      .buttonStyle(.plain)
      .keyboardShortcut(.defaultAction)
      .disabled(!canSubmit || phase == .submitting)
      .accessibilityIdentifier("add-mcp-submit")
    }
  }

  @ViewBuilder
  private var errorRow: some View {
    if let errorMessage {
      HStack(alignment: .top, spacing: OmiSpacing.xs) {
        Image(systemName: "exclamationmark.triangle.fill")
          .scaledFont(size: OmiType.caption)
        Text(errorMessage)
          .scaledFont(size: OmiType.caption)
          .fixedSize(horizontal: false, vertical: true)
      }
      .foregroundColor(Ink.errorRed)
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
          .fill(Ink.errorRed.opacity(0.10))
      )
    }
  }

  private var waitingContent: some View {
    statusCard(
      icon: { ProgressView().scaleEffect(0.6).frame(width: 20, height: 20) },
      title: "Finish authorizing in your browser…",
      detail: "This sheet updates automatically once the server is connected."
    )
  }

  private var canSubmit: Bool {
    guard !name.trimmingCharacters(in: .whitespaces).isEmpty else { return false }
    switch mode {
    case .remote:
      return URL(string: serverUrl.trimmingCharacters(in: .whitespaces))?.host != nil
    case .local:
      return !commandLine.trimmingCharacters(in: .whitespaces).isEmpty
    }
  }

  private var savedLocalContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      statusCard(
        icon: {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.primary)
            .frame(width: 20, height: 20)
        },
        title: "Server saved to ~/.omi/mcp.json",
        detail: "Its tools reach chat automatically — right away, or with your next message if a reply is in flight."
      )

      HStack {
        Spacer()
        Button(action: onDismiss) {
          ConnectionModalActionButton(title: "Done")
        }
        .buttonStyle(.plain)
      }
    }
  }

  /// The one card shape both terminal phases use, so "waiting" and "saved" differ by their words
  /// rather than by their layout.
  private func statusCard<Icon: View>(
    @ViewBuilder icon: () -> Icon,
    title: String,
    detail: String
  ) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      icon()
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(title)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
        Text(detail)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: 0)
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(Ink.rowFill)
    )
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .strokeBorder(Ink.separator, lineWidth: 1)
    )
  }

  private func labeledField<Content: View>(
    _ label: String,
    field: Field,
    hint: String? = nil,
    @ViewBuilder content: () -> Content
  ) -> some View {
    let shape = RoundedRectangle(cornerRadius: PageGlass.fieldRadius, style: .continuous)
    return VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
      content()
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
        .focused($focusedField, equals: field)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(shape.fill(Ink.rowFill))
        .overlay(
          shape.strokeBorder(
            focusedField == field ? Ink.accent : Ink.separator, lineWidth: 1)
        )
        .omiAnimation(.easeOut(duration: 0.12), value: focusedField == field)
      if let hint {
        Text(hint)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private func submit() async {
    // Return-to-submit reaches here from any field, including a half-filled one.
    guard canSubmit, phase != .submitting else { return }
    focusedField = nil
    errorMessage = nil
    do {
      if mode == .local {
        try LocalMcpStore.addCommandServer(
          name: name.trimmingCharacters(in: .whitespaces),
          commandLine: commandLine.trimmingCharacters(in: .whitespaces))
      } else {
        let trimmedKey = apiKey.trimmingCharacters(in: .whitespaces)
        // No key means the server may hand us to the browser for OAuth.
        phase = trimmedKey.isEmpty ? .waitingForAuth : .submitting
        _ = try await LocalMcpStore.addRemoteServer(
          name: name.trimmingCharacters(in: .whitespaces),
          url: serverUrl.trimmingCharacters(in: .whitespaces),
          apiKey: trimmedKey.isEmpty ? nil : trimmedKey)
      }
      await appProvider.fetchUserExtensions()
      phase = .savedLocal
    } catch {
      phase = .editing
      errorMessage = error.localizedDescription
    }
  }
}

// MARK: - Skill editor sheet

/// Create or edit a skill: title plus SKILL.md content, with paste, file pick,
/// and drag-drop input. Saves straight to ~/.omi/skills/<slug>/SKILL.md.
struct SkillEditorSheet: View {
  @ObservedObject var appProvider: AppProvider
  /// nil creates a new skill; non-nil edits an existing one.
  let editingSkill: LocalSkillsStore.Skill?
  let onDismiss: () -> Void

  @State private var title = ""
  @State private var markdown = ""
  @State private var isWorking = false
  @State private var errorMessage: String?
  @State private var isDropTargeted = false
  @State private var confirmingDelete = false

  private static let maxSkillBytes = 128 * 1024

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(editingSkill == nil ? "Add Skill" : "Edit Skill")
            .scaledFont(size: OmiType.title, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text("The assistant reads the name and description, and loads the full instructions when relevant")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer()
        DismissButton(action: onDismiss)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Name")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
        TextField("e.g. Weekly Report Format", text: $title)
          .textFieldStyle(.plain)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.primary)
          .padding(OmiSpacing.sm)
          .background(Ink.rowFill)
          .cornerRadius(OmiChrome.smallControlRadius)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(Ink.separator, lineWidth: 1)
          )
      }

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        HStack {
          Text("Instructions (Markdown)")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
          Spacer()
          Button {
            pickSkillFile()
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "square.and.arrow.down")
              Text("Import .md file")
            }
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
          }
          .buttonStyle(.plain)
        }

        // `Ink.nsPrimary`, not the editor's chat-composer default of white: this well sits on a
        // light surface, where white text is invisible.
        OmiTextEditor(
          text: $markdown,
          textColor: Ink.nsPrimary,
          focusOnAppear: false,
          onFileDrop: { url in
            Task { @MainActor in importSkillFile(url) }
          },
          onFileDragTargeted: { isDropTargeted = $0 }
        )
        .frame(maxHeight: .infinity)
        .padding(OmiSpacing.sm)
        .background(isDropTargeted ? Ink.rowFillHover : Ink.rowFill)
        .cornerRadius(OmiChrome.smallControlRadius)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .stroke(isDropTargeted ? Ink.accent.opacity(0.6) : Ink.separator, lineWidth: isDropTargeted ? 1.5 : 1)
        )
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleDrop)
        .overlay(alignment: .center) {
          if markdown.isEmpty {
            Text("Paste your SKILL.md here, or drop a .md file")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .allowsHitTesting(false)
          }
        }
      }
      .frame(maxHeight: .infinity)

      if let errorMessage {
        Text(errorMessage)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.errorRed)
          .fixedSize(horizontal: false, vertical: true)
      }

      HStack(spacing: OmiSpacing.sm) {
        if editingSkill != nil {
          Button {
            if confirmingDelete {
              Task { await deleteSkill() }
            } else {
              confirmingDelete = true
            }
          } label: {
            Text(confirmingDelete ? "Confirm Delete" : "Delete")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(Ink.errorRed)
              .padding(.horizontal, OmiSpacing.md)
              .frame(height: 28)
              .background(Ink.errorRed.opacity(0.1))
              .cornerRadius(OmiChrome.chipRadius)
          }
          .buttonStyle(.plain)
          .disabled(isWorking)
        }

        Spacer()

        Button {
          Task { await save() }
        } label: {
          if isWorking {
            ProgressView()
              .scaleEffect(0.7)
              .frame(width: 110, height: 32)
          } else {
            Text("Save Skill")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(Ink.surface)
              .frame(width: 110, height: 32)
              .background(canSave ? Ink.primary : Ink.secondary.opacity(0.4))
              .cornerRadius(OmiChrome.controlRadius)
          }
        }
        .buttonStyle(.plain)
        .disabled(!canSave || isWorking)
      }
    }
    .padding(OmiSpacing.lg)
    .background(Ink.surface)
    .task { await loadExisting() }
  }

  private var canSave: Bool {
    !markdown.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      && !title.trimmingCharacters(in: .whitespaces).isEmpty
  }

  private func loadExisting() async {
    guard let editingSkill else { return }
    title = editingSkill.name
    markdown = LocalSkillsStore.loadMarkdown(slug: editingSkill.slug) ?? ""
  }

  private func handleDrop(providers: [NSItemProvider]) -> Bool {
    return ChatAttachmentDropHandler.collectURLs(from: providers) { urls in
      guard let url = urls.first else { return }
      Task { @MainActor in
        importSkillFile(url)
      }
    }
  }

  private func pickSkillFile() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    panel.allowedContentTypes = [.plainText, .text]
    if panel.runModal() == .OK, let url = panel.url {
      importSkillFile(url)
    }
  }

  private func importSkillFile(_ url: URL) {
    guard let data = try? Data(contentsOf: url), data.count <= Self.maxSkillBytes,
      let text = String(data: data, encoding: .utf8)
    else {
      errorMessage = "Could not read that file as text (max 128KB)."
      return
    }
    if let problem = LocalSkillsStore.validationError(forImportedMarkdown: text) {
      errorMessage = problem
      return
    }
    errorMessage = nil
    markdown = text
    if title.trimmingCharacters(in: .whitespaces).isEmpty {
      let base = url.deletingPathExtension().lastPathComponent
      if base.lowercased() != "skill" {
        title = base.replacingOccurrences(of: "-", with: " ").replacingOccurrences(of: "_", with: " ")
      }
    }
  }

  private func save() async {
    guard markdown.utf8.count <= Self.maxSkillBytes else {
      errorMessage = "Skill content is too large (max 128KB)."
      return
    }
    isWorking = true
    defer { isWorking = false }
    errorMessage = nil
    do {
      try LocalSkillsStore.saveSkill(
        title: title, markdown: markdown, replacingSlug: editingSkill?.slug)
      await appProvider.fetchUserExtensions()
      onDismiss()
    } catch {
      errorMessage = error.localizedDescription
    }
  }

  private func deleteSkill() async {
    guard let editingSkill else { return }
    isWorking = true
    defer { isWorking = false }
    LocalSkillsStore.deleteSkill(slug: editingSkill.slug)
    await appProvider.fetchUserExtensions()
    onDismiss()
  }
}

// MARK: - Local MCP server detail sheet

struct LocalMcpDetailSheet: View {
  let server: LocalMcpStore.Entry
  @ObservedObject var appProvider: AppProvider
  let onDismiss: () -> Void

  @State private var confirmingDelete = false
  @State private var isSigningIn = false
  @State private var apiKey = ""
  @State private var errorText: String?
  @State private var notice: String?

  private var status: McpServerProbe.Status {
    appProvider.mcpStatuses[server.name] ?? .checking
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(server.name)
            .scaledFont(size: OmiType.title, weight: .semibold)
            .foregroundColor(Ink.primary)
          // "Local" here used to mean "configured locally", which read as a claim about where a
          // remote server runs.
          Text(server.isCommand ? "Local command" : "Remote server")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        Spacer()
        DismissButton(action: onDismiss)
      }

      Text(server.summary)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.primary)
        .padding(OmiSpacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Ink.rowFill)
        .cornerRadius(OmiChrome.smallControlRadius)

      // A remote server can refuse us for two different reasons, and the fix differs: OAuth needs a
      // browser round trip, an API key needs the key. Both live here because a card that reports
      // "Needs sign-in" with nothing to press is a dead end.
      if !server.isCommand {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          HStack(spacing: OmiSpacing.sm) {
            Text(status.label)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(status.isHealthy ? Ink.primary : Ink.secondary)
            Spacer()
            Button(action: signIn) {
              ConnectionModalActionButton(title: isSigningIn ? "Signing in…" : "Sign In")
            }
            .buttonStyle(.plain)
            .disabled(isSigningIn)
            .accessibilityIdentifier("apps-mcp-sign-in")
          }

          HStack(spacing: OmiSpacing.sm) {
            SecureField("Or paste an API key", text: $apiKey)
              .textFieldStyle(.roundedBorder)
            Button("Save Key", action: saveAPIKey)
              .buttonStyle(.plain)
              .foregroundColor(Ink.secondary)
              .disabled(apiKey.trimmingCharacters(in: .whitespaces).isEmpty)
          }
        }
      }

      if let notice {
        Text(notice)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      if let errorText {
        Text(errorText)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.errorRed)
          .fixedSize(horizontal: false, vertical: true)
      }

      Text(
        "Configured in ~/.omi/mcp.json. Changes reach chat automatically — right away, or with your next message if a reply is in flight."
      )
      .scaledFont(size: OmiType.caption)
      .foregroundColor(Ink.secondary)
      .fixedSize(horizontal: false, vertical: true)

      HStack {
        Spacer()
        Button {
          if confirmingDelete {
            LocalMcpStore.removeServer(name: server.name)
            Task {
              await appProvider.fetchUserExtensions()
              onDismiss()
            }
          } else {
            confirmingDelete = true
          }
        } label: {
          Text(confirmingDelete ? "Confirm Remove" : "Remove")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.errorRed)
            .padding(.horizontal, OmiSpacing.md)
            .frame(height: 28)
            .background(Ink.errorRed.opacity(0.1))
            .cornerRadius(OmiChrome.chipRadius)
        }
        .buttonStyle(.plain)
      }

      Spacer(minLength: 0)
    }
    .padding(OmiSpacing.lg)
    .background(Ink.surface)
  }

  private func signIn() {
    isSigningIn = true
    errorText = nil
    notice = nil
    Task {
      do {
        try await LocalMcpStore.signIn(name: server.name)
        await appProvider.fetchUserExtensions()
        await appProvider.refreshMcpStatuses()
        notice = "Signed in. Its tools reach chat automatically."
      } catch {
        errorText = error.localizedDescription
      }
      isSigningIn = false
    }
  }

  private func saveAPIKey() {
    errorText = nil
    notice = nil
    do {
      try LocalMcpStore.setAPIKey(name: server.name, apiKey: apiKey)
      apiKey = ""
      Task {
        await appProvider.fetchUserExtensions()
        await appProvider.refreshMcpStatuses()
        notice = "Key saved."
      }
    } catch {
      errorText = error.localizedDescription
    }
  }
}
