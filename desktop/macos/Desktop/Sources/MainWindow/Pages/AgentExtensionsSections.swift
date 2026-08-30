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
    .task(id: imageUrl) { image = await ExtensionLogoLoader.shared.image(for: imageUrl) }
  }

  private var symbol: some View {
    Image(systemName: fallbackSymbol)
      .scaledFont(size: OmiType.subheading)
      .foregroundColor(Ink.primary)
  }
}

/// Session cache for catalog logos. The same publisher icon appears on a card and again in the
/// detail sheet, and the grid re-renders on every keystroke of the search field.
actor ExtensionLogoLoader {
  static let shared = ExtensionLogoLoader()

  private var cache: [String: NSImage?] = [:]

  func image(for urlString: String) async -> NSImage? {
    if let cached = cache[urlString] { return cached }
    guard let url = URL(string: urlString), url.scheme == "https" else {
      cache[urlString] = NSImage?.none
      return nil
    }
    var request = URLRequest(url: url, timeoutInterval: 10)
    request.setValue("image/*", forHTTPHeaderField: "Accept")
    let loaded: NSImage? = await {
      guard let (data, response) = try? await URLSession.shared.data(for: request),
        (response as? HTTPURLResponse).map({ (200..<300).contains($0.statusCode) }) == true
      else { return nil }
      return NSImage(data: data)
    }()
    cache[urlString] = loaded
    return loaded
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

  private enum Mode: String, CaseIterable {
    case remote = "Remote URL"
    case local = "Local Command"
  }

  @State private var name = ""
  @State private var serverUrl = ""
  @State private var apiKey = ""
  @State private var commandLine = ""
  @State private var mode: Mode = .remote
  @State private var phase: Phase = .editing
  @State private var errorMessage: String?

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Add MCP Server")
            .scaledFont(size: OmiType.title, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text("Its tools become available to the assistant in chat")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        Spacer()
        DismissButton(action: onDismiss)
      }

      switch phase {
      case .savedLocal:
        savedLocalContent
      case .waitingForAuth:
        waitingContent
      default:
        formContent
      }

      Spacer(minLength: 0)
    }
    .padding(OmiSpacing.lg)
    .background(Ink.surface)
  }

  private var formContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Picker("", selection: $mode) {
        ForEach(Mode.allCases, id: \.self) { Text($0.rawValue).tag($0) }
      }
      .pickerStyle(.segmented)
      .labelsHidden()

      labeledField("Name") {
        TextField(mode == .remote ? "e.g. Linear" : "e.g. Playwright", text: $name)
      }
      if mode == .remote {
        labeledField("Server URL") {
          TextField("https://mcp.example.com/mcp", text: $serverUrl)
        }
        labeledField("API key (optional)") {
          SecureField("Leave empty for public or OAuth servers", text: $apiKey)
        }
      } else {
        labeledField("Command") {
          TextField("npx @playwright/mcp@latest", text: $commandLine)
        }
        Text("Runs this command on your Mac and connects to it as an MCP server. Saved to ~/.omi/mcp.json.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }

      if let errorMessage {
        Text(errorMessage)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.errorRed)
          .fixedSize(horizontal: false, vertical: true)
      }

      HStack {
        Spacer()
        Button {
          Task { await submit() }
        } label: {
          if phase == .submitting {
            ProgressView()
              .scaleEffect(0.7)
              .frame(width: 110, height: 32)
          } else {
            Text("Connect")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(Ink.surface)
              .frame(width: 110, height: 32)
              .background(canSubmit ? Ink.primary : Ink.secondary.opacity(0.4))
              .cornerRadius(OmiChrome.controlRadius)
          }
        }
        .buttonStyle(.plain)
        .disabled(!canSubmit || phase == .submitting)
      }
    }
  }

  private var waitingContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.md) {
        ProgressView()
        Text("Finish authorizing in your browser…")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.primary)
      }
      Text("This window updates automatically once the server is connected.")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .cornerRadius(OmiChrome.smallControlRadius)
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
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "checkmark.circle.fill")
          .scaledFont(size: OmiType.subheading)
          .foregroundColor(Ink.primary)
        Text("Server saved to ~/.omi/mcp.json")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
      }
      Text("Its tools are discovered when the assistant starts its next chat session.")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
      HStack {
        Spacer()
        Button(action: onDismiss) {
          Text("Done")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.surface)
            .frame(width: 110, height: 32)
            .background(Ink.primary)
            .cornerRadius(OmiChrome.controlRadius)
        }
        .buttonStyle(.plain)
      }
    }
  }

  private func labeledField<Content: View>(_ label: String, @ViewBuilder content: () -> Content)
    -> some View
  {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
      content()
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
  }

  private func submit() async {
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

      Text("Configured in ~/.omi/mcp.json. Tools are discovered when the assistant starts its next chat session.")
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
        notice = "Signed in. Tools arrive with the assistant's next chat session."
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
