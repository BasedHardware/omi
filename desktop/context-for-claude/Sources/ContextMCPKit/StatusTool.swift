import ContextCore

extension Tools {
    static func renderStatus(_ status: StatusInfo?, queryFailure: String? = nil) -> String {
        var out: [String] = ["**This Mac — Context for Claude's live capture**", ""]

        guard let status else {
            // The database opened and then refused to answer. That is a reader fault with the file
            // sitting right there, so it must never be phrased as an empty history.
            if let queryFailure {
                out.append("""
                The capture database opened but could not be read: \(queryFailure). This is a fault \
                in this reader — it says nothing about whether the user was recorded. Do not report \
                an empty history.
                """)
                return out.joined(separator: "\n")
            }
            out.append(missingDatabaseSentence(subject: "This reader"))
            return out.joined(separator: "\n")
        }

        let headline: String
        if status.capturing {
            headline = "Context for Claude is capturing right now."
        } else if let reason = status.pausedReason.flatMap(nonEmpty) {
            headline = "Context for Claude is not capturing right now — \(reason)."
        } else {
            headline = "Context for Claude is not capturing right now."
        }

        if status.segmentCount == 0 && status.frameCount == 0 {
            out.append("""
            \(headline) It has recorded nothing locally so far — no speech and no screen text — so an \
            empty answer from `recent` or `activity` means "not captured", never "did not happen".
            """)
        } else {
            out.append("""
            \(headline) It holds \(plural(status.segmentCount, "transcript line")) across \
            \(plural(status.sessionCount, "conversation")) and \
            \(plural(status.frameCount, "screen observation")) on this Mac.
            """)
            out.append("")
            out.append("""
            Local coverage: **\(status.coverage)**. Anything inside that window was recorded here, so \
            an empty local search there is real evidence it did not happen at this Mac. Anything \
            outside it was never captured here — check the Omi account below before concluding \
            anything.
            """)
        }

        // Said whatever the local half holds: the two halves are not equally fresh, and the gap is
        // widest on exactly the data a "what was I just looking at?" question needs.
        out.append("")
        out.append(screenLagStatusLine)

        out.append("")
        if status.capabilities.isEmpty {
            out.append("""
            - No permission report available — Context for Claude is not running, so it cannot say which of \
            microphone, system audio, and screen recording are granted.
            """)
        } else {
            for capability in status.capabilities {
                let state = capability.granted ? "granted" : "not granted"
                let detail = nonEmpty(capability.detail).map { " — \($0)" } ?? ""
                out.append("- **\(capability.name)**: \(state)\(detail)")
            }
            if status.capabilities.contains(where: { !$0.granted }) {
                out.append("")
                out.append("""
                At least one capture permission is off, so a whole class of local context is missing \
                rather than absent. Say that plainly instead of concluding something never happened.
                """)
            }
        }

        out.append("")
        out.append("Database: `\(status.databasePath)`")

        if OmiMemoryStore.shared.isAvailable {
            out.append("")
            out.append("""
            Omi memories: the main Omi app's local database is connected, so `recall` searches \
            memories that have not synced to the backend yet as well as those that have.
            """)
        }
        return out.joined(separator: "\n")
    }

    /// One request is the whole budget for `status`: it establishes reachability and gives a bounded
    /// sample without turning an informational tool into an account-history crawler. The sample is
    /// deliberately never described as the beginning of the record.
    static func historySampleLine(probeOffset: Int, sampledStart: Double?) -> String {
        let depth = number(probeOffset + 1)
        if let sampledStart, sampledStart > 0 {
            return """
            History depth — **this is a sample, not the start of the record.** Context for Claude \
            read a single conversation \(depth) back from the newest one: it starts at \
            \(ContextTime.describe(sampledStart)). That proves the account holds at least \(depth) \
            conversations and reaches at least that far back. It is where this probe stopped, not \
            where the history stops. `recall`, `conversations` and `screen` can still search earlier \
            with `since`.
            """
        }
        return """
        History depth: the probe \(depth) conversations back came back with nothing. That means \
        either the account holds fewer than \(depth) conversations **or** that one request did not \
        succeed — this tool cannot tell which, so it is not a count of the user's history.
        """
    }

    /// The other half of honesty: an unreachable account and an empty account must never read the
    /// same way, and the key's *source* is reportable while its value is not.
    static func renderOmiStatus() -> String {
        let backend = OmiBackend.shared
        guard let source = backend.keySourceLabel else {
            return """
            **The Omi account — history**

            Not configured: no Omi MCP API key was found in the \(OmiKeyResolver.environmentVariable) \
            environment variable or in ~/Library/Application Support/ContextForClaude/mcp-key. \
            The account's conversations and remembered facts cannot be read, so every tool above \
            answers from this Mac's local capture only. That is a missing connection, not an empty \
            life — do not tell the user their history is empty.
            """
        }

        var out: [String] = ["**The Omi account — history**", ""]
        switch backend.history() {
        case let .ok(probe):
            out.append("Reachable. Key source: \(source) — Context for Claude reads that key and never prints, copies, or stores it.")
            out.append("")
            if let newest = probe.newest, let at = newest.startedAt {
                out.append("Newest record in the account: \(ContextTime.describe(at)) — \"\(collapse(newest.title))\".")
            } else {
                out.append("The account is reachable but holds no conversations yet.")
            }
            // `status` is an informational, single-request account check. The bounded probe is
            // already a sample and must stay a sample; walking/bisecting history here turns a
            // status render into up to four hidden remote reads.
            out.append("")
            out.append(
                historySampleLine(
                    probeOffset: probe.probeOffset,
                    sampledStart: probe.atProbeOffset?.startedAt))
            out.append("")
            if let range = backend.seenRange, range.oldest > 0 {
                out.append("Oldest Omi record read in this session: \(ContextTime.describe(range.oldest)).")
            }
            out.append("")
            out.append("""
            `recall`, `conversations`, `transcript` and `screen` read this history and merge it with \
            the local capture above; `recent` and `activity` are local only, by design.
            """)
        case let .unavailable(error):
            out.append("Unreachable: \(error.reason). Key source: \(source).")
            out.append("")
            out.append("""
            Only this Mac's local capture is searchable right now. An empty result from `recall` or \
            `conversations` currently means "the account could not be read", never "it did not \
            happen" — say so rather than concluding anything about the user's history.
            """)
        }
        return out.joined(separator: "\n")
    }
}
