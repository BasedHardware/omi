import ContextCore
import Foundation

/// Whether a remote client may reach the network right now.
///
/// Airgap Mode used to mean exactly one thing — `ExclusionEngine.faviconFetch` — while the app went
/// on POSTing OCR'd screen text every sixty seconds, streaming microphone audio to a websocket, and
/// minting account credentials. A switch named after a promise has to keep it, so the promise is
/// enforced here rather than re-derived at each client: every remote client names itself in
/// ``Client``, asks this type before it opens a socket, and reports the refusal through the shared
/// fallback helper.
///
/// ``Client`` is exhaustive on purpose rather than a free-form string. A remote client that never
/// appears in this list is a client nobody can audit, and the list is what makes "does Airgap Mode
/// actually cover everything?" a question with a checkable answer.
///
/// **The suppression report itself never leaves the Mac.** `ContextTelemetry.recordFallback` writes
/// to `os.Logger` and, only under `CONTEXT_DEBUG=1`, to a local file — see `Support/Telemetry.swift`,
/// which carries the invariant a future remote sink would have to honour. Reporting an airgap
/// suppression over the network would be the exact disclosure Airgap Mode exists to prevent.
enum NetworkEgress {

    /// Every client in this app that opens a connection to something off this Mac.
    ///
    /// "Off this Mac" is the test, not "to Omi". The two entries that are neither an upload nor an
    /// account call are the ones the list was missing for longest, and they are the two that make the
    /// point: the largest single egress this app performs is a ~600 MB model fetch from a third party
    /// that has nothing to do with the user's account, and the client that discloses the most per
    /// byte is a favicon request that names a domain the user asked to hide.
    enum Client: String, Sendable, CaseIterable {
        case signIn = "sign-in"
        case tokenRefresh = "token-refresh"
        case omiAPI = "omi-api"
        case screenActivitySync = "screen-activity-sync"
        case conversationUpload = "conversation-upload"
        case listenSocket = "listen-socket"
        case mcpKeyProvisioning = "mcp-key-provisioning"
        /// The Parakeet CoreML weights, pulled from HuggingFace on first run.
        case speechModelDownload = "speech-model-download"
        /// `https://<an excluded host>/favicon.ico`, drawn beside each website exclusion.
        case faviconFetch = "favicon-fetch"
        /// Sparkle asking `github.com` for this app's own appcast asset, and downloading the release
        /// enclosure it names if a newer build exists. Not an Omi endpoint (updates involve no
        /// backend at all) and not the user's data — but "off this Mac" is the test, not "to Omi", and
        /// a scheduled request every six hours discloses that this app is installed here and which
        /// build is running. See `Update/UpdateEgress.Step` for the three places it is enforced.
        case updateCheck = "update-check"
        /// `context-for-claude-mcp` reading `https://api.omi.me/v1/mcp/*` — a *different process*,
        /// spawned per Claude session, with its own `URLSession`.
        ///
        /// It is in this list even though nothing in this target calls it, and that is the point.
        /// The enumeration is the audited answer to "does Airgap Mode cover everything the product
        /// does?", and a sibling process the app itself launches is part of the product; leaving it
        /// out let `AirgapEgressTests` iterate `allCases` and report full coverage while the largest
        /// per-request disclosure the product makes — the user's own recall queries — was outside
        /// the list entirely. The guard lives where the socket does, in
        /// `ContextMCPKit/OmiBackend.swift`, and answers to `MCPNetworkEgress`; the raw value here
        /// is `OmiBackend.egressClientName`, so the record that process emits and the record this
        /// one would emit are the same line. `ContextApp` cannot link `ContextMCPKit`, so the two
        /// halves are tied by that shared slug and by a test on each side.
        case mcpOmiBackend = "omi-backend"
        /// Product analytics: anonymous counts of launches, permissions, captures and MCP tool calls,
        /// batched to PostHog. See `ContextAnalytics`.
        ///
        /// It is in this list for the same reason `updateCheck` is — "off this Mac" is the test — but
        /// it is the entry with the sharpest edge, because it is the only client whose *entire
        /// purpose* is to describe the person using the app. `ContextAnalytics.record` therefore
        /// **drops** a suppressed event rather than spooling it: every other client here queues its
        /// work and sends it when the switch goes off, and an analytics event that did the same would
        /// mean Airgap Mode delayed the disclosure instead of preventing it. There is no catching up.
        case analytics = "analytics"

        /// The subsystem a suppression is reported under, so the fallback record lands in the same
        /// area as that client's other degradations rather than in an "airgap" bucket of its own.
        var area: ContextFallbackArea {
            switch self {
            case .signIn, .tokenRefresh: return .auth
            case .omiAPI, .screenActivitySync, .conversationUpload: return .upload
            case .listenSocket, .speechModelDownload: return .capture
            case .mcpKeyProvisioning, .mcpOmiBackend: return .mcp
            // Both land in `settings` because that is where the user meets them: the favicon beside
            // an exclusion row, and the Updates row's "Check Now". There is no `updates` area, and
            // adding one for a single client would put a suppression nobody is looking for into a
            // bucket nobody reads.
            case .faviconFetch, .updateCheck: return .settings
            // Analytics is not any one subsystem's degradation — it reports on all of them — so it
            // lands beside the other two clients a user meets in Settings rather than inventing an
            // area that would hold exactly one client.
            case .analytics: return .settings
            }
        }
    }

    /// The decision, as a pure function of the flag — so both answers are drivable in a test
    /// without an engine, a configuration file, or a disk.
    ///
    /// Every client is refused, sign-in included. `client` is taken so a refusal is *attributable*
    /// at the call site and in the log, not so that some client can be excepted: there is no
    /// exception, and an Airgap Mode with a carve-out would be the same broken promise in a smaller
    /// font.
    static func isSuppressed(_ client: Client, airgapMode: Bool) -> Bool {
        airgapMode
    }

    /// Live Airgap Mode. A read, never a cache: the toggle takes effect on the next tick of whatever
    /// asks, which is what lets the Settings row promise "immediately" instead of "after relaunch".
    ///
    /// Note that `ExclusionSet.airgapMode` is also forced on when the exclusion configuration fails
    /// closed (`ExclusionSet.make`), so an unreadable or newer-than-this-build configuration stops
    /// egress too. That is deliberate: a config we cannot parse may carry exclusions we cannot
    /// express, and uploading a frame we might have been told to withhold is unrecoverable.
    static var isAirgapped: Bool { ExclusionEngine.shared.current.airgapMode }

    static func isSuppressed(_ client: Client) -> Bool {
        isSuppressed(client, airgapMode: isAirgapped)
    }

    /// The sentence a person is shown when Airgap Mode is why something did not happen.
    ///
    /// Names the setting and where to change it. A refusal the user cannot connect to a switch they
    /// flipped is indistinguishable from the app being broken.
    static func explanation(_ client: Client) -> String {
        switch client {
        case .signIn, .tokenRefresh:
            return "Airgap Mode is on, so Context for Claude can't reach Omi to sign in. "
                + "Turn it off in Settings › General to sign in."
        case .screenActivitySync, .conversationUpload, .omiAPI, .mcpKeyProvisioning:
            return "Airgap Mode is on, so nothing is being uploaded to your Omi account. "
                + "Everything stays captured on this Mac and syncs when you turn it off."
        case .mcpOmiBackend:
            // Reads, not uploads, and the reader is Claude — so this says what an answer is missing
            // rather than what is queued. The sentence the MCP process actually renders is
            // `MCPNetworkEgress.suppressedReadClause`, written for a model rather than for a
            // Settings row; this is the same promise in this list's voice.
            return "Airgap Mode is on, so Context for Claude's MCP tools aren't reading your Omi "
                + "account. They still answer from what this Mac captured locally."
        case .listenSocket:
            return "Airgap Mode is on, so audio isn't being sent for cloud transcription. "
                + "Transcription continues on this Mac."
        case .speechModelDownload:
            // Says what is off *and* what would turn it back on, because unlike every other client
            // here this one cannot resolve itself by waiting: the weights are not coming while the
            // switch is on, so nothing is transcribed at all until either the switch goes off or the
            // model arrives some other way. Naming the size is what makes the refusal read as a
            // decision the app made on the user's behalf rather than a failure.
            return "Airgap Mode is on, so the ~600 MB speech model can't be downloaded. "
                + "Nothing is transcribed until you turn it off in Settings › General; "
                + "a model already on this Mac keeps working."
        case .faviconFetch:
            return "Airgap Mode is on, so site icons aren't fetched. "
                + "Asking a site for its icon would tell it you excluded it."
        case .updateCheck:
            // Says the version stays put, because the alternative reading — "updates are broken" —
            // is the one that sends someone off to reinstall by hand. This is also the only
            // suppression in this list a user meets by pressing a button, so it has to explain why
            // the button appeared to do nothing.
            return "Airgap Mode is on, so Context for Claude isn't checking for updates. "
                + "It stays on this version until you turn it off in Settings › General."
        case .analytics:
            // Says "not recorded" rather than "not sent", because the difference is the whole point:
            // nothing is being held for later. A person who reads this and turns the switch off
            // should not discover that a week of their activity went up at that moment.
            return "Airgap Mode is on, so no usage counts are recorded. "
                + "Nothing is held back to send later — those days simply aren't measured."
        }
    }

    /// Records that `client` did not run because Airgap Mode is on.
    ///
    /// `outcome` is the caller's judgement and differs by client: work that is still queued and will
    /// go up later is `.degraded`, work that is gone for good is `.dropped`. Nothing in this app
    /// passes `.dropped` for a *user* artefact — see each call site.
    static func recordSuppression(_ client: Client, outcome: ContextFallbackOutcome) {
        #if DEBUG
        observer?(client, outcome)
        #endif
        ContextTelemetry.recordFallback(
            area: client.area,
            from: client.rawValue,
            to: "suppressed",
            reason: "airgap-mode",
            outcome: outcome)
    }

    #if DEBUG
    /// Every suppression this app records, offered here before it reaches the log.
    ///
    /// It exists because of `MCPKeyProvisioner.retire`, which refused correctly and reported
    /// nothing for as long as it existed. A guard is the conspicuous half of a suppression and the
    /// record is the half nobody misses until the telemetry is read, so "was it gated?" and "did it
    /// say so?" have to be separately checkable — and `ContextTelemetry` writes to `os.Logger`,
    /// which a test cannot read back.
    ///
    /// DEBUG-only and `nil` in production: this is a way to *watch* the one writer, not a second
    /// one. A test that sets it must clear it again, or the next test inherits its recorder.
    nonisolated(unsafe) static var observer: ((Client, ContextFallbackOutcome) -> Void)?
    #endif
}
