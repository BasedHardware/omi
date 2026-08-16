import Foundation

/// The standing instruction in the user's **global** Claude memory: check this Mac's context before
/// answering, on every prompt, without being asked.
///
/// **Why this exists when there is already an MCP server and a skill.** The server's `instructions`
/// ride on `initialize` and describe what the tools *are*. ``ClaudeSkill`` is read when an agent is
/// already shopping for a skill. Neither is a *habit*: both are things Claude consults once it has
/// decided the question might need outside context, and the failure this product keeps hitting is
/// the decision itself — a user types "fix it" or "why is this broken", Claude reads that as a
/// question about the current chat, and answers from nothing. `~/.claude/CLAUDE.md` is the one file
/// Claude Code loads into *every* prompt in *every* project, which makes it the only place a "always
/// look first" rule can actually live. Reported as: *"edit user's memory in Claude which it uses for
/// every prompt … and even in CLAUDE.md globally for everything first call Context for Claude. It
/// should happen automatically."*
///
/// **This is the user's file, not ours.** It may already carry hundreds of lines of their own
/// standing instructions, and it is loaded into every session they run — a bad write here is a bad
/// write into all of their work. So the same rule as ``ClaudeConfig``: own one block, byte for byte,
/// and treat every other byte as untouchable. The block is delimited by HTML comments, which render
/// as nothing in Markdown, and both `merged(into:)` and `stripped(from:)` are pure functions over a
/// string so that "what does this do to a file that already had one / had none / had ours twice" is
/// answerable without a home directory.
public enum ClaudeMemory {

    /// `~/.claude/CLAUDE.md` — the personal memory, so it applies to every project rather than to
    /// one checkout. Which is the point: context about the user's life is not repository-scoped.
    public static var documentURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".claude", isDirectory: true)
            .appendingPathComponent("CLAUDE.md")
    }

    /// The fences. Comments rather than a heading, so the block is invisible in any Markdown
    /// renderer and unmistakable to this code — a heading called "Context for Claude" is something a
    /// user might reasonably type themselves, and we must never edit a section they wrote.
    public static let beginMarker = "<!-- BEGIN Context for Claude — managed block, edits here are overwritten -->"
    public static let endMarker = "<!-- END Context for Claude -->"

    /// What the block says.
    ///
    /// Written as a rule with a trigger and a refusal, not as an advertisement. The three parts are
    /// deliberate: *when* (every prompt, not "when it seems relevant" — that judgement is the thing
    /// that fails), *what to call*, and *what never to say*, because the observed failure mode is a
    /// confident "I don't have access to that" from a machine that is holding the answer.
    public static let instruction = """
        ## Context for Claude (this Mac)

        This Mac runs Context for Claude, which continuously records what this user says, hears and
        has on screen, and serves it over the `context-for-claude` MCP server along with their Omi
        history. **Treat it as part of your context, not as a fallback.**

        **Before you answer, plan, ask a clarifying question, or touch code, check it.** Every time,
        without being asked:

        - `recent` — the last minutes of speech and screen. Use it whenever a request assumes
          something you were not given: "fix it", "this is broken", "help me with this", "like we
          said", "follow up with them".
        - `recall` — search everything by name: a person, project, product, bug, decision, price.
          Use it for every proper noun in the request that you have no record of.
        - `look` — the screen itself, as an image, for anything visual, and to check your own UI work
          after you build it.
        - `status` — call this **before** telling the user something was not recorded.

        **Never tell this user you lack context, that you can only see this conversation, or ask them
        to paste or re-explain something they have already lived through — search first.** Terse or
        vague input is the signal to go and look, not to ask. If the record genuinely has nothing,
        say so explicitly, then ask.

        Say in one line which context you used.
        """

    /// The block as it appears in the file, markers included.
    public static var block: String {
        "\(beginMarker)\n\n\(instruction)\n\n\(endMarker)"
    }

    // MARK: - Document manipulation (pure)

    /// Adds the block, or replaces the one that is already there, leaving every other byte alone.
    ///
    /// **Replacement, not append, and that is the whole reason the markers exist.** Connecting is
    /// idempotent and happens on every launch that finds the config out of date, so an append would
    /// grow the user's global memory by a copy of this text every time — in the one file that is
    /// loaded into every prompt they ever run, where the cost is tokens on every request forever.
    ///
    /// A file whose block is malformed — an opening marker with no close, which is what a
    /// half-finished hand edit looks like — is **left completely alone** except for the block being
    /// appended fresh at the end. Slicing from a marker to the end of a file the user has edited
    /// would delete whatever they wrote after it, and losing their standing instructions is not a
    /// recoverable failure. See ``ClaudeConfig/merged(into:mcpBinaryPath:)`` for the same tie-break.
    public static func merged(into existing: String) -> String {
        guard let range = blockRange(in: existing) else {
            let trimmed = existing.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? "\(block)\n" : "\(trimmed)\n\n\(block)\n"
        }
        return existing.replacingCharacters(in: range, with: block)
    }

    /// Takes the block back out, leaving the rest — including the user's own blank-line habits
    /// around it — as close to untouched as removing a paragraph allows.
    public static func stripped(from existing: String) -> String {
        guard let range = blockRange(in: existing) else { return existing }
        let without = existing.replacingCharacters(in: range, with: "")
        let trimmed = without.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "" : "\(trimmed)\n"
    }

    /// Whether `existing` already carries exactly this build's block. Content equality rather than
    /// presence, like ``ClaudeSkill/isInstalled``: a block from an older version names tools that may
    /// no longer exist, and reporting it as installed is what would make it permanent.
    public static func isInstalled(in existing: String) -> Bool {
        guard let range = blockRange(in: existing) else { return false }
        return String(existing[range]) == block
    }

    /// The span from the opening marker through the closing one, or nil when there is not a
    /// well-formed pair. Searched from the *first* opening marker and the *last* closing one, so a
    /// file that somehow ended up with two blocks collapses to one on the next write rather than
    /// keeping the duplicate forever.
    private static func blockRange(in text: String) -> Range<String.Index>? {
        guard let start = text.range(of: beginMarker),
            let end = text.range(of: endMarker, options: .backwards),
            start.lowerBound < end.lowerBound
        else { return nil }
        return start.lowerBound..<end.upperBound
    }

    // MARK: - Disk

    /// Writes the block into `~/.claude/CLAUDE.md`, creating the file and its directory if needed.
    ///
    /// Returns whether anything changed, so connecting twice does not touch a file the user may have
    /// open in an editor.
    ///
    /// - Parameter url: the file to write. Defaulted to ``documentURL`` and injected only so the
    ///   disk half of this type is exercisable — the pure merge above is the interesting logic, but
    ///   "creates `~/.claude` when it is missing", "leaves an unchanged file alone" and "deletes a
    ///   file that was only ever ours" are properties of *this* function, and a test that could not
    ///   reach them would leave the only part that touches the user's disk unproven.
    @discardableResult
    public static func install(at url: URL = documentURL) throws -> Bool {
        let existing = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
        guard !isInstalled(in: existing) else { return false }
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try write(merged(into: existing), to: url)
        return true
    }

    /// Removes the block. The file itself stays unless the block was the only thing in it — an empty
    /// `CLAUDE.md` we created and then emptied is litter, but a file the user has written in is
    /// theirs whatever is left after our paragraph goes.
    @discardableResult
    public static func remove(at url: URL = documentURL) throws -> Bool {
        guard let existing = try? String(contentsOf: url, encoding: .utf8),
            blockRange(in: existing) != nil
        else { return false }
        let remaining = stripped(from: existing)
        if remaining.isEmpty {
            try FileManager.default.removeItem(at: url)
        } else {
            try write(remaining, to: url)
        }
        return true
    }

    public static var isInstalled: Bool {
        guard let existing = try? String(contentsOf: documentURL, encoding: .utf8) else { return false }
        return isInstalled(in: existing)
    }

    /// Atomic, for the same reason `ClaudeConfig.writeDocument` is: a crash or a full disk part-way
    /// through must not leave the user with half of their global instructions.
    private static func write(_ text: String, to url: URL) throws {
        try text.write(to: url, atomically: true, encoding: .utf8)
    }
}
