import AppKit
import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

// MARK: - MCP Servers section

/// User-added MCP servers from ~/.omi/mcp.json, listed on the Apps page next
/// to Imports/Exports.
struct McpServersSection: View {
  @ObservedObject var appProvider: AppProvider
  let onAdd: () -> Void
  let onSelectLocal: (LocalMcpStore.Entry) -> Void

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

      if appProvider.localMcpServers.isEmpty {
        AgentExtensionEmptyCard(
          icon: "server.rack",
          text: "No servers yet. Add a remote URL, or a local command like npx @playwright/mcp@latest.")
      } else {
        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 260), spacing: OmiSpacing.md)],
          alignment: .leading,
          spacing: OmiSpacing.md
        ) {
          ForEach(appProvider.localMcpServers) { server in
            AgentExtensionCard(
              icon: server.isCommand ? "terminal" : "server.rack",
              imageUrl: "",
              title: server.name,
              subtitle: server.isCommand ? "Local command" : "Local config",
              detail: server.summary,
              statusText: "Active in chat",
              statusActive: true
            ) {
              onSelectLocal(server)
            }
          }
        }
      }
    }
  }

}

// MARK: - Skills section

/// User-authored skills (SKILL.md in ~/.omi/skills), listed on the Apps page.
struct SkillsSection: View {
  @ObservedObject var appProvider: AppProvider
  let onAdd: () -> Void
  let onSelect: (LocalSkillsStore.Skill) -> Void

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

      if appProvider.localSkills.isEmpty {
        AgentExtensionEmptyCard(
          icon: "graduationcap",
          text: "No skills yet. Paste or drop a SKILL.md, or write one from scratch.")
      } else {
        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 260), spacing: OmiSpacing.md)],
          alignment: .leading,
          spacing: OmiSpacing.md
        ) {
          ForEach(appProvider.localSkills) { skill in
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
    }
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

          ImportConnectorActionButton(title: "Manage", isConnected: true)
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
    if let url = URL(string: imageUrl), !imageUrl.isEmpty {
      AsyncImage(url: url) { image in
        image.resizable().aspectRatio(contentMode: .fit)
      } placeholder: {
        fallbackIcon
      }
      .frame(width: 40, height: 40)
      .cornerRadius(OmiChrome.smallControlRadius)
    } else {
      fallbackIcon
    }
  }

  private var fallbackIcon: some View {
    Image(systemName: icon)
      .scaledFont(size: OmiType.subheading)
      .foregroundColor(Ink.primary)
      .frame(width: 40, height: 40)
      .background(Ink.wash)
      .cornerRadius(OmiChrome.smallControlRadius)
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
    .padding(OmiSpacing.xxl)
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

        OmiTextEditor(text: $markdown, focusOnAppear: false)
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
    .padding(OmiSpacing.xxl)
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

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(server.name)
            .scaledFont(size: OmiType.title, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text(server.isCommand ? "Local command server" : "Local server")
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
    .padding(OmiSpacing.xxl)
    .background(Ink.surface)
  }
}
