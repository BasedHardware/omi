import ContextCore
import Foundation

/// The whitelist of what may leave this Mac in a Sentry payload, and nothing else.
///
/// This is the entire disclosure. `beforeSend` hands every event the SDK is about to send through
/// `apply` — crash events included, because those are *converted* by the SDK on the launch after
/// the crash and pass through the same hook (the exception's frames, the thread list, the loaded
/// image list — all of it arrives here first). Whatever `apply` returns is what the wire carries.
///
/// ## Why a whitelist and not a blocklist
///
/// A crash payload is assembled by the SDK from machine state this app does not control: exception
/// reason strings are `NSException`/`NSError` text, thread names are strings other code set, frame
/// and image fields carry absolute paths from the reporting Mac, and local variable capture can
/// hold anything that was in scope. Enumerating what is dangerous loses that game; the only stable
/// rule is "these fields, and no others". Every field not named as kept is dropped, and the drop
/// list below is documentation, not enforcement.
///
/// ## What symbolication actually needs
///
/// Mapping a crash frame back to a source line takes exactly three things: the frame's instruction
/// address, its image's load address, and the image's UUID (plus the dSYM uploaded for that UUID).
/// Function names help humans read the result; everything else in a frame — source file paths,
/// source snippets, local variables, the binary's path on the reporting Mac — is disclosure with
/// no diagnostic return, and none of it survives this policy.
///
/// **The unit tests construct hostile payloads** — a user's home directory in an exception value,
/// a transcript-shaped thread name, a local-variable dictionary — and assert the fields are gone.
/// That is the contract this file exists to keep.
struct ContextSentryEventSnapshot: Sendable, Equatable {

    /// A crash's exception chain. `value` is deliberately absent from the *scrubbed* form: it is
    /// free text (`NSException` reasons and `NSError` messages end up here verbatim), it is not
    /// needed for symbolication, and the `type` alone still groups issues.
    struct Exception: Sendable, Equatable {
        var type: String
        var value: String?
        var mechanismType: String?
        var mechanismHandled: Bool?
    }

    /// One thread. `name` is dropped by `apply`: thread names are arbitrary strings set by
    /// whatever created the thread, and nothing in triage needs them.
    struct Thread: Sendable, Equatable {
        var id: Int64?
        var crashed: Bool?
        var current: Bool?
        var isMain: Bool?
        var frames: [Frame]
    }

    /// One stack frame, reduced to symbolication's inputs and a human-readable function name.
    /// Dropped by `apply`: `fileName` and `module`/`package` (absolute paths from the reporting
    /// Mac), `contextLine`/`preContext`/`postContext` (source snippets), `vars` (locals — the
    /// widest leak in a raw crash payload), line/column numbers.
    struct Frame: Sendable, Equatable {
        var instructionAddress: String?
        var imageAddress: String?
        var symbolAddress: String?
        var function: String?
        var inApp: Bool?
    }

    /// One loaded image. The UUID is what symbolication keys on — it is how Sentry matches a
    /// frame's addresses to the uploaded dSYM. `name` and `codeFile` are paths on the reporting
    /// Mac and are dropped by `apply`.
    struct DebugImage: Sendable, Equatable {
        var uuid: String?
        var type: String?
        var imageAddress: String?
        var imageVmAddress: String?
        var imageSize: Int64?
    }

    // Kept verbatim: build identity and SDK metadata.
    var eventType: String?
    var level: String?
    var platform: String?
    var releaseName: String?
    var dist: String?
    var environment: String?
    var sdkName: String?
    var sdkVersion: String?

    /// The event's message, if any — gated through ``ContextSentryPolicy/sanitizedMessage(_:)``:
    /// only this app's slug vocabulary survives, because a message is free text like an exception
    /// value is.
    var message: String?

    /// Gated through ``ContextSentryPolicy/sanitizedFingerprint(_:)``: this app's own
    /// closed-vocabulary triple survives, arbitrary SDK- or scope-supplied fingerprints do not.
    var fingerprint: [String]?

    // Everything below is either rebuilt from a whitelist (tags, context) or dropped outright
    // (user, breadcrumbs, extra, request, modules, serverName) by `apply`.
    var tags: [String: String]?
    var context: [String: [String: String]]?
    var exceptions: [Exception]?
    var threads: [Thread]?
    var debugMeta: [DebugImage]?
    var user: String?
    var breadcrumbCount: Int?
    var extraKeys: [String]?
    var hasRequest: Bool?
    var serverName: String?
    var modules: [String]?
}

/// The scrubbed form `ContextSentryPolicy.apply` returns: exactly what may be sent.
///
/// Fields the whitelist drops are absent rather than emptied — the adapter that maps this back
/// onto the SDK event assigns `nil` for them, so "dropped" has one spelling.
struct ContextSentryScrubbedEvent: Sendable, Equatable {
    var eventType: String?
    var level: String?
    var platform: String?
    var releaseName: String?
    var dist: String?
    var environment: String?
    var sdkName: String?
    var sdkVersion: String?
    var message: String?
    var fingerprint: [String]?
    var tags: [String: String]
    var context: [String: [String: String]]
    var exceptions: [ContextSentryEventSnapshot.Exception]
    var threads: [ContextSentryEventSnapshot.Thread]
    var debugMeta: [ContextSentryEventSnapshot.DebugImage]
}

/// The drop-and-scrub rules, as pure functions.
///
/// Extracted from the SDK-facing adapter for the same reason Omi desktop's `beforeSend` decision
/// lives in `SentryBeforeSendPolicy`: the filter list must be testable without constructing SDK
/// objects, and a rule that lives next to the SDK import tends to grow SDK-shaped exceptions.
enum ContextSentryPolicy {

    /// The only tag this app vouches for. It is the same discriminator the analytics carry, and
    /// it is what keeps this project's issues attributable to this product and not another's.
    static let appTag = "context-for-claude"

    /// The only contexts kept, by key, and the only subfields within them.
    ///
    /// `device.name` — the user's own name for their Mac, e.g. "Alice's MacBook Pro" — is the
    /// field this whitelist exists to drop; the SDK sets it by default. Model/family/arch answer
    /// "which hardware crashes", which is the whole question.
    static let keptContexts: [String: Set<String>] = [
        "os": ["name", "version", "build"],
        "device": ["model", "family", "arch"],
        "app": ["app_identifier", "app_name", "app_version", "app_build"],
    ]

    /// Whether an event may be sent at all.
    ///
    /// The SDK is only ever started in the shipping app, so this is defence in depth rather than
    /// the gate — but it is cheap, it is the same shape as the analytics refusals, and a guard
    /// that exists only as an invariant someone remembers is not a guard.
    static func shouldDrop(isShippingBundle: Bool) -> Bool {
        !isShippingBundle
    }

    #if DEBUG
    /// Test seam for the live bundle check, same shape as the gate's seams: `nil` (production)
    /// means `ContextPaths.isShippingBundle` decides. The real-SDK traffic test sets `true` so
    /// `beforeSend` — which is armed with this check in production too — runs against the SDK in
    /// the test process. Tests must clear it again.
    nonisolated(unsafe) static var isShippingBundleForTests: Bool?
    #endif

    /// The live bundle check `beforeSend` consults.
    static func liveIsShippingBundle() -> Bool {
        #if DEBUG
        if let isShippingBundleForTests { return isShippingBundleForTests }
        #endif
        return ContextPaths.isShippingBundle
    }

    /// The prefix every message this app itself constructs carries. A message is free text — the
    /// same reason exception values are dropped — so only slugs in this vocabulary survive.
    static let handledMessagePrefix = "cfc-fallback "
    /// The first element of a fingerprint this app constructs; the two following elements are the
    /// `area` and `reason` enum raw values (see `ContextSentryHandledReport`).
    static let fingerprintVocabularyPrefix = "cfc-fallback"

    /// A message is kept only when it is one of this app's slugs: `cfc-fallback area=… reason=…
    /// outcome=…`, built from closed enums. Anything else — an SDK-synthesized message, a
    /// `logger.error("…")` string that reached an event — is dropped, because it is arbitrary text
    /// and this integration's contract is a closed diagnostic vocabulary.
    static func sanitizedMessage(_ raw: String?) -> String? {
        guard let raw, raw.hasPrefix(handledMessagePrefix) else { return nil }
        return raw
    }

    /// A fingerprint is kept only when it is exactly this app's triple — `["cfc-fallback", area,
    /// reason]`, three elements, the last two non-empty (enum raw values). Any other fingerprint,
    /// from any source, is dropped rather than forwarded: grouping for crash events is derived by
    /// Sentry from the scrubbed exception `type`s, and an arbitrary fingerprint would both leak
    /// whatever built it and pin unrelated crashes into one issue.
    static func sanitizedFingerprint(_ raw: [String]?) -> [String]? {
        guard let raw = raw, raw.count == 3, raw[0] == fingerprintVocabularyPrefix,
            !raw[1].isEmpty, !raw[2].isEmpty
        else { return nil }
        return raw
    }

    /// The whitelist. Returns exactly what may be sent; everything else is dropped.
    ///
    /// Kept verbatim: `eventType`, `level`, `platform`, `releaseName`, `dist`, `environment`,
    /// `sdkName`, `sdkVersion` — build and SDK identity. Vocabulary-gated: `message` (only this
    /// app's slugs) and `fingerprint` (only this app's triple). Rebuilt from a whitelist: `tags`
    /// (only `app`), `context` (only `keptContexts`, and only string subfields — a numeric or
    /// nested value under an allowed key is still dropped rather than coerced). Dropped outright:
    /// `user`, `breadcrumbs`, `extra`, `request`, `modules`, `serverName`, exception `value`s,
    /// thread `name`s, frame paths/snippets/locals, image `name`/`codeFile`.
    static func apply(_ event: ContextSentryEventSnapshot) -> ContextSentryScrubbedEvent {
        var tags: [String: String] = [:]
        if let app = event.tags?[Self.appTag] { tags[Self.appTag] = app }

        var context: [String: [String: String]] = [:]
        for (name, allowedKeys) in Self.keptContexts {
            guard let values = event.context?[name] else { continue }
            var kept: [String: String] = [:]
            for key in allowedKeys {
                if let value = values[key] { kept[key] = value }
            }
            if !kept.isEmpty { context[name] = kept }
        }

        let exceptions = (event.exceptions ?? []).map { exception in
            ContextSentryEventSnapshot.Exception(
                type: exception.type,
                value: nil,
                mechanismType: exception.mechanismType,
                mechanismHandled: exception.mechanismHandled)
        }

        let threads = (event.threads ?? []).map { thread in
            ContextSentryEventSnapshot.Thread(
                id: thread.id,
                crashed: thread.crashed,
                current: thread.current,
                isMain: thread.isMain,
                frames: thread.frames.map { frame in
                    ContextSentryEventSnapshot.Frame(
                        instructionAddress: frame.instructionAddress,
                        imageAddress: frame.imageAddress,
                        symbolAddress: frame.symbolAddress,
                        function: frame.function,
                        inApp: frame.inApp)
                })
        }

        let debugMeta = (event.debugMeta ?? []).map { image in
            ContextSentryEventSnapshot.DebugImage(
                uuid: image.uuid,
                type: image.type,
                imageAddress: image.imageAddress,
                imageVmAddress: image.imageVmAddress,
                imageSize: image.imageSize)
        }

        return ContextSentryScrubbedEvent(
            eventType: event.eventType,
            level: event.level,
            platform: event.platform,
            releaseName: event.releaseName,
            dist: event.dist,
            environment: event.environment,
            sdkName: event.sdkName,
            sdkVersion: event.sdkVersion,
            message: Self.sanitizedMessage(event.message),
            fingerprint: Self.sanitizedFingerprint(event.fingerprint),
            tags: tags,
            context: context,
            exceptions: exceptions,
            threads: threads,
            debugMeta: debugMeta)
    }
}
