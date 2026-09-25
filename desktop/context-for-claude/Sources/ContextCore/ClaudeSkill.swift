import Foundation

/// The Claude Code skill that teaches every agent — main loop and subagent alike — that this
/// machine's context is available and when to reach for it.
///
/// **Why a skill exists at all when the MCP server already ships `instructions`.** Those
/// instructions ride on `initialize` and land in the main loop's system prompt. A subagent is a
/// fresh context: it is handed a task and none of the conversation that produced it, so it is
/// simultaneously the reader with the least context and the one least likely to think of asking for
/// more. It also cannot read the tool descriptions until it is already shopping for a tool. A skill
/// is the one artefact both surfaces enumerate by name and description before any of that, which
/// makes it the only place a habit can be set for an agent nobody has briefed.
///
/// This is a guest in the user's `~/.claude`, and the same rule applies here as in ``ClaudeConfig``:
/// touch one directory, own every byte in it, and leave everything else alone. The skill lives in
/// its own folder named for this app, is rewritten only when its content actually changes, and is
/// deleted whole when the user disconnects.
public enum ClaudeSkill {
    /// The skill's directory name, which is also the name Claude lists it under.
    ///
    /// Split per build for the same reason as ``ClaudeConfig/serverName``: this is a directory a dev
    /// build would otherwise overwrite and, on disconnect, delete out from under the installed app.
    public static let name = name(forBundle: ContextPaths.bundleIdentifier)

    public static func name(forBundle bundleIdentifier: String) -> String {
        ContextPaths.isDevelopmentBuild(bundleIdentifier)
            ? "context-for-claude-dev" : "context-for-claude"
    }

    /// `~/.claude/skills/context-for-claude`
    ///
    /// The personal-skills location, so it applies to every project the user opens rather than to
    /// one checkout. Context about their life is not repository-scoped.
    public static var directoryURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".claude/skills", isDirectory: true)
            .appendingPathComponent(name, isDirectory: true)
    }

    /// `~/.claude/skills/context-for-claude/SKILL.md`
    public static var documentURL: URL {
        directoryURL.appendingPathComponent("SKILL.md")
    }

    /// The skill, verbatim.
    ///
    /// The frontmatter `description` is doing most of the work: it is what an agent reads when
    /// deciding whether to open the skill at all, so it is written as a list of the situations that
    /// should trigger it rather than as a summary of what the skill contains.
    public static let document = """
        ---
        name: \(name)
        description: >-
          Read what this user has actually said, heard, and had on screen — and look at their real
          screen as an image. Use whenever a request assumes context you were not given ("this",
          "that error", "help me with this"), names a person, project, meeting or decision you have
          no record of, asks what they were doing or reading, or is visual ("does this look right",
          "the spacing is off"). Also use to check your own UI work by looking at it after you build
          it. Available to subagents, which should use it instead of reporting missing context.
        ---

        # Context for Claude

        This Mac runs Context for Claude, which continuously records what the user says, hears, and
        has on screen, and serves it over the `\(ClaudeConfig.serverName)` MCP server together with their
        full Omi account history. **You are not limited to the current conversation.** Never tell
        this user you cannot see what they were doing, or ask them to paste something back that they
        have already lived through — call a tool instead.

        ## The tools

        | Tool | Use it for |
        |---|---|
        | `recall` | Search everything by name or topic — a person, project, decision, price, place. The first thing to try when a request names something you have no record of. |
        | `recent` | The last N minutes of speech and screen. The only tool that sees the current session in full; the account lags by minutes. |
        | `look` | **The screen itself, as an image.** Anything visual, and how you check your own UI work. |
        | `screen` | The *text* that was on screen, searchable and filterable by app. Use over `look` when you need to find something across hours. |
        | `conversations` / `transcript` | Find a conversation, then read it line by line. Use before writing anything that must be faithful to a call. |
        | `activity` | Where the time went — app and window blocks with totals. Standups, timesheets, weekly reviews. |
        | `status` | What was and was not recorded. Call this **before** telling the user something never happened. |
        | `get_memories` | The durable facts Omi has learned about them, listed directly. |
        | `create_memory` / `edit_memory` / `delete_memory` | Write to Omi's canonical memory store when they tell you something worth keeping, correct a fact, or ask you to forget one. |

        ## When to reach for them

        - **A request that assumes context.** "Help me with this", "why is this failing", "draft a
          reply", "summarise that". They mean something in front of them. `recent`, or `look`.
        - **A name you do not know.** A person, a company, a project, a meeting. `recall` before
          asking them to explain.
        - **Anything visual.** "This looks wrong", "is that aligned", "the spacing is off". `look`.
          Do not ask for a screenshot; take one.
        - **Checking your own work.** After changing a UI, build it, run it, and `look` at it. A
          layout you reasoned about is a guess. Report what you saw, not what should have happened.
        - **Before concluding something did not happen.** `status` reports which windows of time
          were recorded, which is what separates "did not happen" from "was not captured".

        ## Reading results honestly

        - Hits marked `live` were captured on this Mac and are exact full-text matches. Hits marked
          `omi` come from a semantic search with no relevance floor — it always returns its nearest
          neighbours, even when nothing matches — so treat those as leads to confirm, not evidence.
        - A `look` result always states the age of the frame it returned. An unchanged screen writes
          no new frame, so an old frame usually means "nothing changed" — but right after you
          launched or changed something, it means capture has not caught up. Look again.
        - A transcript line marked uncertain may not be speech at all. Never quote it.
        - A `look` result with no picture and a redaction note is redaction working: a credential was
          visible on that screen. Say that, rather than reporting a broken capture.

        ## If you are a subagent

        You were given a task and none of the conversation behind it. That makes these tools *more*
        useful to you, not less. When the task refers to something you were not told — a person, a
        file, a decision, a screen — call them before reporting that you lack context.

        ## If you are dispatching subagents

        They do not inherit what you have already looked up. Either pass the context into the prompt,
        or tell them explicitly that these tools exist and to use them.
        """

    /// Writes the skill, creating `~/.claude/skills/context-for-claude` if needed.
    ///
    /// Returns whether anything was written: an unchanged document is left alone so the file's
    /// modification date keeps meaning "when the skill last changed", and so connecting twice does
    /// not churn a file the user may have open.
    @discardableResult
    public static func install() throws -> Bool {
        let url = documentURL
        if let existing = try? String(contentsOf: url, encoding: .utf8), existing == document {
            return false
        }
        try FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        try document.write(to: url, atomically: true, encoding: .utf8)
        return true
    }

    /// Removes the skill and its directory.
    ///
    /// The whole directory, because this app created it and nothing else writes into it — leaving an
    /// empty folder behind in the user's skills list is litter that looks like a broken skill.
    /// Anything unexpected inside it is left alone by `removeItem` failing, which is the right way
    /// to lose this argument.
    ///
    /// Returns whether there was anything to remove.
    @discardableResult
    public static func remove() throws -> Bool {
        guard FileManager.default.fileExists(atPath: documentURL.path) else { return false }
        try FileManager.default.removeItem(at: directoryURL)
        return true
    }

    /// Whether the installed skill is the one this build ships.
    ///
    /// Content equality rather than mere presence, for the same reason ``ClaudeConfig/isRegistered``
    /// compares the binary path: a skill left over from an older version describes tools that may no
    /// longer exist, and reporting it as installed is what would make it permanent.
    public static var isInstalled: Bool {
        (try? String(contentsOf: documentURL, encoding: .utf8)) == document
    }
}
