import ContextCore
import Foundation

/// Whether this process may reach the network right now.
///
/// `context-for-claude-mcp` is a **different process** from the app. Claude spawns it, it holds its
/// own `URLSession`, and no decision the app makes in memory reaches it. Airgap Mode is enforced in
/// the app by `NetworkEgress` (`Sources/ContextApp/Backend/NetworkEgress.swift`) — and for a while
/// that was the whole of the enforcement, so a user who turned the switch on silenced the app and
/// left this binary reading `api.omi.me` on every `recall`. A promise kept in one process and broken
/// in the sibling it spawns is not a promise; this type is the other half of it.
///
/// **There is exactly one remote client in this target** — ``OmiBackend`` for
/// `https://api.omi.me/v1/mcp/*`. Everything else the MCP tools do is local or passes through this
/// client: the capture database, the main Omi app's `omi.db` (``OmiMemoryStore``), and the query
/// stamp. Neither
/// `ContextCore` nor `ContextMCP` opens a socket. That is why suppressing egress here costs a tool
/// its *account* half and never its answer — and it is a property worth re-checking rather than
/// assuming, because it is what makes this switch safe to honour unconditionally.
enum MCPNetworkEgress {

    /// Airgap Mode, read from disk at the moment of asking.
    ///
    /// **The re-read is the point.** ``ExclusionEngine`` loads the configuration once at
    /// construction and then serves it from memory — right for the app, where Settings mutates that
    /// memory directly, and wrong here, where the switch is flipped in another process entirely. A
    /// value cached when this binary started would mean a Claude session opened *before* the user
    /// reached for the switch keeps talking to the network for as long as the session lasts, which
    /// is exactly the window a person reaches for that switch in. `ExclusionEngine.reload()` is
    /// documented for precisely this case: "for an external edit, or a second process".
    ///
    /// **Fails closed, and inherits that rather than restating it.** `ExclusionSet.make` forces
    /// `airgapMode` on whenever the configuration is unreadable, malformed, or written by a newer
    /// build, so this answers `true` in every case where we cannot prove the user left the switch
    /// off. A configuration this build cannot parse may carry exclusions it cannot express, and a
    /// request sent under that uncertainty cannot be taken back. A Mac with *no* configuration file
    /// — every install that exists today — is `.defaultsOnly`, which is not fail-closed: the gate
    /// must not silence an account nobody asked it to silence.
    ///
    /// The cost is one small JSON file read per remote request. Measured against the request it
    /// gates — bounded at `OmiBackend.requestTimeout`, ten seconds — it does not register, and it is
    /// paid only when this process was about to open a socket.
    ///
    /// `engine` is a parameter so a test can point a real engine at a real file it controls and
    /// watch this answer change underneath it. On `.shared` the reload's other effects (the
    /// generation bump, the observer callbacks) are inert: nothing else in this process reads
    /// exclusions.
    static func isAirgapped(engine: ExclusionEngine = .shared) -> Bool {
        engine.reload()
        return engine.current.airgapMode
    }

    /// The sentence a suppressed read carries back to the model, and through it to the user.
    ///
    /// It has to do two things an empty result cannot: say that *nothing was asked*, so an absence
    /// is never read as an answer about the account; and name the switch and where it lives, because
    /// a refusal a person cannot connect to something they turned on is indistinguishable from the
    /// product being broken. Phrased as a clause because it is rendered inside
    /// `OmiBackendError.reason`'s carrier sentences.
    static let suppressedReadClause = """
    Airgap Mode is on in Context for Claude, so no request was sent — the account was not contacted \
    at all, and nothing here is evidence about what it holds. Turn Airgap Mode off in Context for \
    Claude's Settings › General (menu bar icon › Settings) to read it again
    """

    /// Appended wherever a tool would otherwise tell the reader to sign in.
    ///
    /// The app suppresses sign-in and MCP key provisioning under the same switch
    /// (`NetworkEgress.Client.signIn`, `.mcpKeyProvisioning`), so "sign in and this will work" is
    /// advice that cannot be followed until the switch is off. Nil when the switch is off, so the
    /// ordinary signed-out message stays exactly as it was.
    static var signInBlockedNote: String? {
        guard isAirgapped() else { return nil }
        return """
        Signing in will not help while Airgap Mode is on — Context for Claude suppresses sign-in \
        and key provisioning too. Turn Airgap Mode off in its Settings › General first.
        """
    }

    /// Records that a remote read did not happen because Airgap Mode is on.
    ///
    /// **The shared `recordFallback` helper is not reachable from this target.**
    /// `ContextTelemetry.recordFallback` and `ContextLog` live in `Sources/ContextApp/Support/`,
    /// inside the app's *executable* target; `ContextMCPKit` depends on `ContextCore` only, and an
    /// executable target cannot be depended on. So this emits the helper's exact line shape —
    /// `[fallback] area=… from=… to=… reason=… outcome=…`, the same closed vocabulary — to the one
    /// diagnostic channel this process has. Unifying them means moving `ContextTelemetry` down into
    /// `ContextCore`, which is a shared file this change does not own.
    ///
    /// `outcome=degraded` rather than `dropped`: the tool still answers, from local capture, and the
    /// flag is re-read on the next call, so nothing is lost — only the account half is missing.
    ///
    /// **stderr, and fixed slugs only.** stdout is the JSON-RPC channel and a stray byte there drops
    /// the connection. And this process handles transcripts and screen text: the endpoint path would
    /// carry conversation ids and the query would carry the user's own words, so neither is logged —
    /// there is nothing here but constants.
    static func recordSuppression() {
        // Interpolated rather than spelled out, so the slug this process reports under and the one
        // `NetworkEgress.Client.mcpOmiBackend` audits in the app cannot drift apart silently. The two
        // targets cannot see each other's types; this constant is the whole of the contract.
        MCPServer.note(
            "[fallback] area=mcp from=\(OmiBackend.egressClientName) to=suppressed "
                + "reason=airgap-mode outcome=degraded")
    }
}
