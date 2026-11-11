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

        let headline = Self.headline(for: status)

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

        // Before the permission list, because it is the sharper fact: a permission that reads
        // "granted" over a stream that has produced nothing all day is precisely the combination
        // this tool used to report as a healthy recorder.
        if let failing = Self.failingStreamsBlock(status) {
            out.append("")
            out.append(failing)
        }

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

    /// **The sentence a model reasons from, and the one that was wrong for twenty-nine hours.**
    ///
    /// "Context for Claude is capturing right now" came off a boolean that was true whenever *any*
    /// sensor was alive. With a live microphone and a Screen Recording grant macOS had silently
    /// dropped, this tool told Claude the Mac was being recorded — and `Queries.status` had already
    /// thrown away the one sentence that said otherwise, because it cleared `pausedReason` whenever
    /// `capturing` was true. Everything downstream then answered "what was I looking at?" from a
    /// screen record that had stopped the previous afternoon.
    ///
    /// So the middle case gets its own sentence, and the sentence names the half that is down. A
    /// model that reads it can say "your audio is recorded, your screen is not" instead of guessing.
    static func headline(for status: StatusInfo) -> String {
        switch status.health {
        case .capturing:
            // Intel cloud-ASR gap while sensors stay live must stay visible.
            return status.localCaptureHeadline
        case .degraded:
            let live = status.streams.filter { $0.state.isLive }.map { streamPhrase($0.name) }
            let down = status.streams.filter { $0.state == .blocked || $0.state == .stalled }
                .map { streamPhrase($0.name) }
            let recording = live.isEmpty ? "part of what it records" : sentenceList(live)
            let missing = down.isEmpty ? "part of what it records" : sentenceList(down)
            return """
                Context for Claude is only **partly** capturing right now: \(recording) \
                \(live.count == 1 ? "is" : "are") being recorded and \(missing) \
                \(down.count == 1 ? "is" : "are") not. Anything that would have come from the \
                stopped half is missing rather than absent — do not read it as something that did \
                not happen.
                """
        case .off:
            if let reason = status.pausedReason.flatMap(nonEmpty) {
                return "Context for Claude is not capturing right now — \(reason)."
            }
            return "Context for Claude is not capturing right now."
        }
    }

    /// The per-stream detail, listed only for the streams that are failing. A stream that is off
    /// because the user switched it off is in the permission list below and needs no alarm; a stream
    /// that was working and has stopped needs its own line and its own sentence.
    static func failingStreamsBlock(_ status: StatusInfo) -> String? {
        let failing = status.streams.filter { $0.state == .blocked || $0.state == .stalled }
        guard !failing.isEmpty else { return nil }
        var lines = ["**Capture that has stopped working:**"]
        for stream in failing {
            let word = stream.state == .stalled ? "producing nothing" : "blocked"
            let detail = nonEmpty(stream.detail ?? "").map { " — \($0)" } ?? ""
            let last = stream.lastOutputAt.map {
                " Last produced anything \(ContextTime.describe($0))."
            } ?? " It has produced nothing at all in this session."
            lines.append("- **\(streamPhrase(stream.name))**: \(word)\(detail).\(last)")
        }
        return lines.joined(separator: "\n")
    }

    /// The `StreamName` raw values as a reader meets them.
    static func streamPhrase(_ name: String) -> String {
        switch name {
        case StreamName.microphone: return "the microphone"
        case StreamName.systemAudio: return "call and system audio"
        case StreamName.screen: return "screen capture"
        case StreamName.storage: return "the local database"
        default: return name
        }
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
            var out = """
            **The Omi account — history**

            Not configured: no Omi MCP API key was found in the \(OmiKeyResolver.environmentVariable) \
            environment variable or in ~/Library/Application Support/ContextForClaude/mcp-key. \
            The account's conversations and remembered facts cannot be read, so every tool above \
            answers from this Mac's local capture only. That is a missing connection, not an empty \
            life — do not tell the user their history is empty.
            """
            // `status` is the tool a reader is sent to when something seems wrong, so it is the last
            // place that may leave a live switch unmentioned. With a key present the airgap reports
            // itself through `history()`'s failure below; with no key there is no request to fail,
            // and the reader would otherwise be told to go and sign in — which the same switch
            // blocks.
            if let blocked = MCPNetworkEgress.signInBlockedNote { out += "\n\n" + blocked }
            return out
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
