@testable import ContextApp
import Foundation
import XCTest

/// The whitelist contract, against hostile payloads.
///
/// These payloads are constructed the way a real crash event is shaped — exception values that
/// carry `NSError` text, thread names set by arbitrary code, frames with absolute paths, captured
/// locals, user context — and the assertions are about *absence* in the scrubbed output. This file
/// is the mirror-struct half of the evidence; the real-SDK serialized-traffic audit in
/// `ContextSentrySDKTrafficTests` proves the adapter applies the same rules before serialization.
final class ContextSentryPolicyTests: XCTestCase {

    /// A crash-shaped payload with a leak in every field the whitelist exists to drop.
    private func hostileSnapshot() -> ContextSentryEventSnapshot {
        ContextSentryEventSnapshot(
            eventType: "error",
            level: "fatal",
            platform: "cocoa",
            releaseName: "context-for-claude@1.2.3+1002003",
            dist: "1002003",
            environment: "production",
            sdkName: "sentry.cocoa",
            sdkVersion: "8.58.0",
            message: "uncaught exception 'NSRangeException', reason: 'index 9 beyond bounds'",
            fingerprint: ["some", "arbitrary", "fingerprint"],
            tags: ["context-for-claude": "context-for-claude", "freeform": "/Users/alice/secret"],
            context: [
                "device": ["name": "Alice's MacBook Pro", "model": "Mac16,1", "arch": "arm64e"],
                "os": ["name": "macOS", "version": "15.3", "build": "24D60"],
                "app": ["app_identifier": "com.omi.context-for-claude", "app_version": "1.2.3"],
                "trace": ["trace_id": "0123abcd", "span_id": "fffe"],
            ],
            exceptions: [
                ContextSentryEventSnapshot.Exception(
                    type: "NSRangeException",
                    value: "index 9 beyond bounds — /Users/alice/Documents/notes.txt",
                    mechanismType: "crash",
                    mechanismHandled: false)
            ],
            threads: [
                ContextSentryEventSnapshot.Thread(
                    id: 0, crashed: true, current: true, isMain: true,
                    frames: [
                        ContextSentryEventSnapshot.Frame(
                            instructionAddress: "0x104abc000", imageAddress: "0x104a00000",
                            symbolAddress: "0x104abc123", function: "ContextApp.render(frame:)",
                            inApp: true),
                        ContextSentryEventSnapshot.Frame(
                            instructionAddress: "0x104abc010", imageAddress: "0x104a00000",
                            symbolAddress: nil, function: "main", inApp: true),
                    ])
            ],
            debugMeta: [
                ContextSentryEventSnapshot.DebugImage(
                    uuid: "AB12CD34-0000-0000-0000-000000000000", type: "macho",
                    imageAddress: "0x104a00000", imageVmAddress: "0x0", imageSize: 1_048_576)
            ],
            // Everything below is what the policy must *drop*:
            user: "alice@example.com",
            breadcrumbCount: 3,
            extraKeys: ["transcript", "system_prompt"],
            hasRequest: true,
            serverName: "Alices-MacBook-Pro.local",
            modules: ["ContextApp": "1.2.3"])
    }

    func testHostilePayloadKeepsOnlySymbolicationAndIdentity() throws {
        let scrubbed = ContextSentryPolicy.apply(hostileSnapshot())

        // Identity survived, verbatim.
        XCTAssertEqual(scrubbed.eventType, "error")
        XCTAssertEqual(scrubbed.level, "fatal")
        XCTAssertEqual(scrubbed.platform, "cocoa")
        XCTAssertEqual(scrubbed.releaseName, "context-for-claude@1.2.3+1002003")
        XCTAssertEqual(scrubbed.dist, "1002003")
        XCTAssertEqual(scrubbed.environment, "production")
        XCTAssertEqual(scrubbed.sdkName, "sentry.cocoa")
        XCTAssertEqual(scrubbed.sdkVersion, "8.58.0")

        // Symbolication's inputs survived: exception type (not value), frame addresses and
        // function, image UUID.
        XCTAssertEqual(scrubbed.exceptions.count, 1)
        let exception = try XCTUnwrap(scrubbed.exceptions.first)
        XCTAssertEqual(exception.type, "NSRangeException")
        XCTAssertNil(exception.value, "exception values are free text — dropped")
        XCTAssertEqual(exception.mechanismType, "crash")
        XCTAssertEqual(exception.mechanismHandled, false)
        let frame = try XCTUnwrap(scrubbed.threads.first?.frames.first)
        XCTAssertEqual(frame.instructionAddress, "0x104abc000")
        XCTAssertEqual(frame.imageAddress, "0x104a00000")
        XCTAssertEqual(frame.symbolAddress, "0x104abc123")
        XCTAssertEqual(frame.function, "ContextApp.render(frame:)")
        XCTAssertEqual(frame.inApp, true)
        XCTAssertEqual(
            scrubbed.debugMeta.first?.uuid, "AB12CD34-0000-0000-0000-000000000000")

        // Context subfields are whitelisted per key: the device *name* is gone, the hardware
        // identity is not; an unknown context (trace) is gone entirely.
        XCTAssertEqual(scrubbed.context["device"], ["model": "Mac16,1", "arch": "arm64e"])
        XCTAssertEqual(scrubbed.context["os"], ["name": "macOS", "version": "15.3", "build": "24D60"])
        XCTAssertEqual(
            scrubbed.context["app"],
            ["app_identifier": "com.omi.context-for-claude", "app_version": "1.2.3"])
        XCTAssertNil(scrubbed.context["trace"])

        // Tags reduced to the one this app vouches for.
        XCTAssertEqual(scrubbed.tags, ["context-for-claude": "context-for-claude"])

        // The arbitrary fingerprint and the free-text message are gone: crash grouping is
        // derived from the scrubbed exception types, and the message carried a raw NSException
        // reason.
        XCTAssertNil(scrubbed.fingerprint)
        XCTAssertNil(scrubbed.message)
    }

    func testHostilePayloadDropsEverythingWithNoDiagnosticReturn() {
        let snapshot = hostileSnapshot()
        // The audit fields document what the *input* carried, so the assertions above cannot
        // pass vacuously: the hostile values were present before `apply`.
        XCTAssertEqual(snapshot.user, "alice@example.com")
        XCTAssertEqual(snapshot.breadcrumbCount, 3)
        XCTAssertEqual(snapshot.extraKeys, ["transcript", "system_prompt"])
        XCTAssertEqual(snapshot.hasRequest, true)
        XCTAssertEqual(snapshot.serverName, "Alices-MacBook-Pro.local")
        XCTAssertNotNil(snapshot.modules)

        let scrubbed = ContextSentryPolicy.apply(snapshot)
        // `ContextSentryScrubbedEvent` has no field for any of these — type-level, not value-
        // level: the scrubbed form cannot carry a user, breadcrumbs, extras, a request, a server
        // name, or modules at all.
        XCTAssertFalse(
            Mirror(reflecting: scrubbed).children.contains { label in
                ["user", "breadcrumbs", "extra", "request", "serverName", "modules"]
                    .contains(label ?? "")
            })
    }

    func testHandledVocabularySurvivesWhitelist() {
        // A handled report's message and fingerprint — the bounded area/outcome/reason pair the
        // whole integration reports through — are in-vocabulary and survive.
        var snapshot = hostileSnapshot()
        snapshot.message = "cfc-fallback area=upload reason=provider-5xx outcome=degraded"
        snapshot.fingerprint = ["cfc-fallback", "upload", "provider-5xx"]

        let scrubbed = ContextSentryPolicy.apply(snapshot)
        XCTAssertEqual(
            scrubbed.message, "cfc-fallback area=upload reason=provider-5xx outcome=degraded")
        XCTAssertEqual(scrubbed.fingerprint, ["cfc-fallback", "upload", "provider-5xx"])
    }

    func testOutOfVocabularyMessageAndFingerprintAreDropped() {
        var snapshot = hostileSnapshot()

        // Near-misses are still out of vocabulary: wrong prefix, wrong arity, empty components.
        snapshot.message = "Provider failed: 5xx (see transcript below)"
        snapshot.fingerprint = ["provider-5xx"]
        var scrubbed = ContextSentryPolicy.apply(snapshot)
        XCTAssertNil(scrubbed.message)
        XCTAssertNil(scrubbed.fingerprint)

        snapshot.fingerprint = ["cfc-fallback", "upload", "", "extra"]
        scrubbed = ContextSentryPolicy.apply(snapshot)
        XCTAssertNil(scrubbed.fingerprint)

        snapshot.fingerprint = ["cfc-fallback", "upload", ""]
        scrubbed = ContextSentryPolicy.apply(snapshot)
        XCTAssertNil(scrubbed.fingerprint)
    }

    func testNonShippingBundleIsDroppedEntirely() {
        XCTAssertTrue(ContextSentryPolicy.shouldDrop(isShippingBundle: false))
        XCTAssertFalse(ContextSentryPolicy.shouldDrop(isShippingBundle: true))
    }

    func testEmptyContextsProduceNoEmptyDictionaries() {
        var snapshot = hostileSnapshot()
        snapshot.context = nil
        snapshot.exceptions = nil
        snapshot.threads = nil
        snapshot.debugMeta = nil
        let scrubbed = ContextSentryPolicy.apply(snapshot)
        XCTAssertTrue(scrubbed.context.isEmpty)
        XCTAssertTrue(scrubbed.exceptions.isEmpty)
        XCTAssertTrue(scrubbed.threads.isEmpty)
        XCTAssertTrue(scrubbed.debugMeta.isEmpty)
    }
}
