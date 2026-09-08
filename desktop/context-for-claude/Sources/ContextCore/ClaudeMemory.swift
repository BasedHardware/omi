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
    ///
    /// **A development build owns a different pair**, because these markers are what `write` replaces:
    /// sharing them would mean a locally built app silently overwrote the installed release's block
    /// in the user's global memory, and describing whichever binary happened to launch last. Each
    /// build now manages only its own block. The release strings are byte-identical to what has
    /// already shipped — changing those would orphan every block written by an installed copy.
    public static let beginMarker = beginMarker(forBundle: ContextPaths.bundleIdentifier)
    public static let endMarker = endMarker(forBundle: ContextPaths.bundleIdentifier)

    /// The rules over a stated identifier. Taken as a parameter rather than read from the ambient
    /// bundle because under `swift test` the resolved identifier *is* the shipping one — a guard
    /// written against the ambient value passes whether or not the split exists, which is no guard.
    public static func beginMarker(forBundle bundleIdentifier: String) -> String {
        ContextPaths.isDevelopmentBuild(bundleIdentifier)
            ? "<!-- BEGIN Context for Claude Dev — managed block, edits here are overwritten -->"
            : "<!-- BEGIN Context for Claude — managed block, edits here are overwritten -->"
    }

    public static func endMarker(forBundle bundleIdentifier: String) -> String {
        ContextPaths.isDevelopmentBuild(bundleIdentifier)
            ? "<!-- END Context for Claude Dev -->"
            : "<!-- END Context for Claude -->"
    }

    /// What the block says.
    ///
    /// Written as a rule with a trigger and a refusal, not as an advertisement. The three parts are
    /// deliberate: *when* (every prompt, not "when it seems relevant" — that judgement is the thing
    /// that fails), *what to call*, and *what never to say*, because the observed failure mode is a
    /// confident "I don't have access to that" from a machine that is holding the answer.
    public static let instruction = instruction(forServer: ClaudeConfig.serverName)

    /// The block's text over a stated server name, for the same reason the markers take one.
    public static func instruction(forServer serverName: String) -> String {
        """
        ## Context for Claude (this Mac)

        This Mac runs Context for Claude, which continuously records what this user says, hears and
        has on screen, and serves it over the `\(serverName)` MCP server along with their Omi
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
    }

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
        let ranges = blockRanges(in: existing)
        guard let first = ranges.first else {
            // **`existing` is appended to verbatim, never trimmed.** Trimming it discarded leading
            // indentation and trailing whitespace the user may have meant — in a file this app does
            // not own. Only an all-whitespace file is special-cased, because there is nothing there
            // to preserve and a block preceded by three blank lines is our litter, not theirs.
            guard !existing.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return "\(block)\n"
            }
            let separator = existing.hasSuffix("\n") ? "\n" : "\n\n"
            return "\(existing)\(separator)\(block)\n"
        }
        // Later duplicates removed back to front, so the earlier indices stay valid.
        var out = existing
        for range in ranges.dropFirst().reversed() {
            out = out.replacingCharacters(in: range, with: "")
        }
        return out.replacingCharacters(in: first, with: block)
    }

    /// Takes the block back out, leaving the rest — including the user's own blank-line habits
    /// around it — as close to untouched as removing a paragraph allows.
    public static func stripped(from existing: String) -> String {
        let ranges = blockRanges(in: existing)
        guard !ranges.isEmpty else { return existing }
        var without = existing
        for range in ranges.reversed() {
            without = without.replacingCharacters(in: range, with: "")
        }
        let trimmed = without.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "" : "\(trimmed)\n"
    }

    /// Whether `existing` already carries exactly this build's block. Content equality rather than
    /// presence, like ``ClaudeSkill/isInstalled``: a block from an older version names tools that may
    /// no longer exist, and reporting it as installed is what would make it permanent.
    public static func isInstalled(in existing: String) -> Bool {
        let ranges = blockRanges(in: existing)
        // Exactly one, so a file that somehow ended up with two blocks is *not* reported as correct
        // and the next install collapses it.
        guard ranges.count == 1 else { return false }
        return String(existing[ranges[0]]) == block
    }

    /// Every well-formed block in the file, in order, with malformed regions skipped.
    ///
    /// **An opening marker is only ever paired with a closing one that arrives before the next
    /// opening marker**, and that rule is the whole of this function. The first version took the
    /// first opening marker and the *last* closing one, to collapse duplicates — which meant a file
    /// carrying an orphaned opening marker (a half-finished hand edit) followed by a real block
    /// reported one span running from the orphan straight through to the real block's close.
    /// Everything between them, including whatever the user had written there, was inside the range
    /// that `merged` replaces and `stripped` deletes. So the damaged file this type already refused
    /// to slice on the *first* install lost text on the second.
    ///
    /// An orphan is stepped over rather than closed, and the caller preserves it: `merged` appends a
    /// fresh block after it and never touches it again. Duplicates are still collapsed, but by
    /// returning each pair separately and letting `merged` remove the extras.
    private static func blockRanges(in text: String) -> [Range<String.Index>] {
        var ranges: [Range<String.Index>] = []
        var searchFrom = text.startIndex
        while let begin = text.range(of: beginMarker, range: searchFrom..<text.endIndex) {
            let rest = begin.upperBound..<text.endIndex
            let nextBegin = text.range(of: beginMarker, range: rest)
            guard let end = text.range(of: endMarker, range: rest),
                nextBegin == nil || end.lowerBound < nextBegin!.lowerBound
            else {
                // Nothing closes this one before the next block opens: an orphan. Step past the
                // marker itself and keep looking, so a later well-formed block is still found.
                searchFrom = begin.upperBound
                continue
            }
            ranges.append(begin.lowerBound..<end.upperBound)
            searchFrom = end.upperBound
        }
        return ranges
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
        // **A file that exists and cannot be read is not an empty file.** `try?` collapsed the two,
        // so a `CLAUDE.md` behind a permissions problem, a bad encoding or an I/O error was treated
        // as absent and *overwritten* with our block alone — the user's standing instructions gone,
        // silently, in the one file every session of theirs loads. Only "no such file" may become
        // the empty string; anything else is rethrown before a single byte is written.
        let existing: String
        do {
            existing = try String(contentsOf: url, encoding: .utf8)
        } catch {
            guard !FileManager.default.fileExists(atPath: url.path) else { throw error }
            existing = ""
        }
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
            !blockRanges(in: existing).isEmpty
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
