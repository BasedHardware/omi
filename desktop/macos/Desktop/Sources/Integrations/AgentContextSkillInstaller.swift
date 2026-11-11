import Foundation

/// Installs the small routing guide that teaches local coding agents when to use
/// the Omi MCP server they have just connected.
///
/// The hosted MCP server remains the data authority. This file contains no user
/// context or credential; it only points the agent at the tools exposed by that
/// server. Existing user-authored skills are preserved verbatim.
enum AgentContextSkillInstaller {
  static var document: String {
    """
    ---
    name: omi
    description: Retrieve Omi memories, conversations, people, commitments, screen history, and same-Mac context when the user's request depends on their life or work history.
    ---

    # Omi Agent Skill

    Use this skill whenever a request depends on context the user has already lived through: a person, conversation, decision, commitment, project, screen, transcription, or recent activity. Retrieve it before asking the user to repeat themselves.

    ## Discovery

    - Hosted MCP: list available tools before use. If `get_user_profile` exists, use it for a high-level summary. If it is absent or returns `profile: null`, use `get_memories(limit=5)` and `search_memories`.
    - Local Omi CLI: run `omi --json local status` and `omi --json local tools` before local work. If status fails, Omi Desktop, the local URL, or the local token is not ready.

    ## Routing

    - Hosted MCP: durable memories, synced conversations, people, commitments, preferences, projects, goals, chat history, and synced screen activity.
    - Local CLI: this Mac's screen history, screenshots, app/window activity, local transcriptions, read-only SQL, daily recaps, indexed files, local goals, and tasks.
    - Use `search_conversations` for synced meetings, calls, and remembered events. Use local transcription tables only for recent same-Mac or unsynced local history.
    - Use `get_people` for relationship context, `get_action_items` for commitments, and `get_screen_activity` for synced screen history.
    - Use `omi --json local search-screen` for fuzzy Rewind/OCR questions. Use `omi --json local screenshot` only after a result returns a screenshot ID and the screenshot tool is present.
    - Use `omi --json local sql` for read-only counts, exact filters, local transcriptions, action items, indexed files, goals, and database questions.
    - Use `omi --json local task search` only if task tools are listed.
    - Use `omi --json local task complete` or `omi --json local task delete --yes` only when the user clearly asked you to complete or delete that task. If task tools are absent, do not mutate tasks.
    - Use `omi --json local call <tool> --args-json '{...}'` only when a listed local tool is not covered by a friendly command.
    - Create, edit, or delete hosted memories only after explicit user intent.

    ## Verification Checklist

    - Hosted MCP tools are listed.
    - Hosted memory query succeeds with `get_memories(limit=5)` or equivalent.
    - Local status succeeds with `omi --json local status`.
    - Local tools are listed with `omi --json local tools`.
    - Route only to tools that were discovered.
    - Treat semantic-search results as leads. Confirm important claims against the returned memory, conversation, or screen evidence before presenting them as fact.

    ## Write Discipline

    - Do not create, edit, complete, or delete Omi memories or local tasks unless the user clearly asked for that change.
    - Prefer proposing the memory or task change first when intent is ambiguous.
    - Never treat transient screen activity as a durable memory without explicit user intent or strong evidence.

    ## Setup

    Hosted MCP endpoint: \(MemoryExportDestination.mcpServerURL)
    Authorization header: Bearer <omi_mcp_key>
    Config-file MCP clients should prefer `mcp-remote` with the endpoint and Authorization header above.

    Local Omi Desktop CLI:
    - Install or update `omi-cli`.
    - Configure local access with `omi local configure --url <local_api_url> --token <omi_local_key>`.
    """
  }

  enum Outcome: Equatable {
    case installed
    case unchanged
    case preservedExisting
  }

  static func install(
    for destination: MemoryExportDestination,
    home: URL = FileManager.default.homeDirectoryForCurrentUser
  ) throws -> Outcome? {
    guard let skillsDirectory = skillsDirectory(for: destination, home: home) else {
      return nil
    }

    let skillDirectory = skillsDirectory.appendingPathComponent("omi", isDirectory: true)
    let skillURL = skillDirectory.appendingPathComponent("SKILL.md")
    let document = Self.document

    if let existing = try? String(contentsOf: skillURL, encoding: .utf8) {
      return existing == document ? .unchanged : .preservedExisting
    }

    try FileManager.default.createDirectory(
      at: skillDirectory,
      withIntermediateDirectories: true,
      attributes: nil
    )
    try document.write(to: skillURL, atomically: true, encoding: .utf8)
    return .installed
  }

  static func skillURL(
    for destination: MemoryExportDestination,
    home: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> URL? {
    skillsDirectory(for: destination, home: home)?
      .appendingPathComponent("omi", isDirectory: true)
      .appendingPathComponent("SKILL.md")
  }

  private static func skillsDirectory(
    for destination: MemoryExportDestination,
    home: URL
  ) -> URL? {
    switch destination {
    case .claudeCode:
      return home.appendingPathComponent(".claude/skills", isDirectory: true)
    case .codex:
      return home.appendingPathComponent(".codex/skills", isDirectory: true)
    case .notion, .obsidian, .chatgpt, .claude, .gemini, .agents, .openclaw, .hermes:
      return nil
    }
  }
}
