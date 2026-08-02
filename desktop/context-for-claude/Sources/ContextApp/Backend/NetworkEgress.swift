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

        /// The subsystem a suppression is reported under, so the fallback record lands in the same
        /// area as that client's other degradations rather than in an "airgap" bucket of its own.
        var area: ContextFallbackArea {
            switch self {
            case .signIn, .tokenRefresh: return .auth
            case .omiAPI, .screenActivitySync, .conversationUpload: return .upload
            case .listenSocket, .speechModelDownload: return .capture
            case .mcpKeyProvisioning: return .mcp
            case .faviconFetch: return .settings
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
        }
    }

    /// Records that `client` did not run because Airgap Mode is on.
    ///
    /// `outcome` is the caller's judgement and differs by client: work that is still queued and will
    /// go up later is `.degraded`, work that is gone for good is `.dropped`. Nothing in this app
    /// passes `.dropped` for a *user* artefact — see each call site.
    static func recordSuppression(_ client: Client, outcome: ContextFallbackOutcome) {
        ContextTelemetry.recordFallback(
            area: client.area,
            from: client.rawValue,
            to: "suppressed",
            reason: "airgap-mode",
            outcome: outcome)
    }
}
