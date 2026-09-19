@testable import ContextApp
import Foundation
import Sentry
import XCTest

/// The real SDK, serialized traffic, audited at the admission point.
///
/// `SentrySDK` is started here — crash handler **off**, everything else exactly as production
/// configures it (`SentrySDKReporting.apply`) — with the real gated `URLSession` whose forwarder
/// is a canned protocol. The envelope bytes this test inspects are the bytes the gate would put on
/// the wire: captured where the admission decision is made, after `beforeSend`, after the SDK's
/// own serialization. That is the difference between "our struct is clean" (mirror tests) and
/// "the SDK's payload is clean" — the thing this integration actually promises.
final class ContextSentrySDKTrafficTests: XCTestCase {

    private var cacheRoot: URL!

    override func setUpWithError() throws {
        try super.setUpWithError()
        ContextSentryGate.entryOverride = false
        ContextSentryGate.liveSuppression = { false }
        ContextSentryGate.forwarderOverride = { configuration in
            configuration.protocolClasses = [CannedForwarder.self]
            return URLSession(configuration: configuration)
        }
        ContextSentryPolicy.isShippingBundleForTests = true
        CannedForwarder.reset()
        CannedForwarder.handler = { _ in (200, [:], Data()) }

        cacheRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("cfc-sentry-traffic-\(UUID().uuidString)", isDirectory: true)
    }

    override func tearDown() {
        SentrySDK.close()
        ContextSentryPolicy.isShippingBundleForTests = nil
        ContextSentryGate.resetTestSeams()
        CannedForwarder.reset()
        try? FileManager.default.removeItem(at: cacheRoot)
        super.tearDown()
    }

    /// Starts the real SDK the way production does, minus the native crash handler — installing
    /// one inside a test process is the one thing this suite must not do.
    private func startSDK() {
        let options = Options()
        SentrySDKReporting.apply(
            ContextSentry.StartOptions(
                dsn: "https://public-key@sentry.invalid/42",
                releaseName: "context-for-claude@0.0.0-test+1",
                dist: "1",
                environment: "production",
                cacheRoot: cacheRoot.path),
            to: options)
        options.enableCrashHandler = false
        SentrySDK.start(options: options)
    }

    /// Captures an event and returns the decoded JSON payloads of the `event` envelope items the
    /// gate admitted — the serialized bytes, not the in-memory event.
    private func capturedEventPayloads() throws -> [[String: Any]] {
        SentrySDK.flush(timeout: 10)

        let requests = CannedForwarder.receivedRequests
        XCTAssertFalse(
            requests.isEmpty,
            "no envelope crossed the gate; the pipeline from capture to send is broken")

        var payloads: [[String: Any]] = []
        for request in requests {
            let body = try XCTUnwrap(request.bodyData, "envelope request carried no body")
            let item = try XCTUnwrap(Self.envelopeEventItem(body))
            let json = try XCTUnwrap(
                JSONSerialization.jsonObject(with: item) as? [String: Any])
            payloads.append(json)
        }
        return payloads
    }

    // MARK: Envelope parsing
    //
    // An envelope is: a header line (JSON), then per item a header line (JSON with `length`) and
    // that many payload bytes.

    private static func envelopeEventItem(_ data: Data) -> Data? {
        var bytes = [UInt8](data)

        func readLine() -> [UInt8]? {
            guard let newline = bytes.firstIndex(of: UInt8(ascii: "\n")) else { return nil }
            let line = Array(bytes[..<newline])
            bytes.removeSubrange(0...newline)
            return line
        }

        guard readLine() != nil else { return nil }  // envelope header: event_id
        while !bytes.isEmpty {
            guard let itemHeaderLine = readLine(),
                let itemHeader = try? JSONSerialization.jsonObject(with: Data(itemHeaderLine))
                    as? [String: Any],
                let length = itemHeader["length"] as? Int,
                bytes.count >= length
            else { return nil }
            let payload = Array(bytes[0..<length])
            bytes.removeSubrange(0..<length)
            if itemHeader["type"] as? String == "event" { return Data(payload) }
        }
        return nil
    }

    private static func valuesArray(
        _ payload: [String: Any], under key: String
    ) -> [[String: Any]] {
        (payload[key] as? [String: Any])?["values"] as? [[String: Any]] ?? []
    }

    // MARK: The audits

    func testHandledEventSerializedPayloadCarriesOnlyWhitelistedFields() throws {
        startSDK()

        let report = ContextSentryHandledReport(
            area: .upload, outcome: .degraded, reason: .unavailable)
        SentrySDK.capture(event: SentrySDKReporting.makeEvent(report))

        for payload in try capturedEventPayloads() {
            // The bounded diagnostic identity: the slug message, the vocabulary fingerprint, the
            // one tag, the level.
            let message = payload["message"] as? [String: String]
            XCTAssertEqual(
                message?["formatted"],
                "cfc-fallback area=upload reason=unavailable outcome=degraded")
            XCTAssertEqual(payload["fingerprint"] as? [String], ["cfc-fallback", "upload", "unavailable"])
            XCTAssertEqual(payload["tags"] as? [String: String], ["context-for-claude": "context-for-claude"])
            XCTAssertEqual(payload["level"] as? String, "warning")

            // Nothing else — no identity, no ambient context, no extras of any spelling.
            for forbidden in ["user", "breadcrumbs", "extra", "request", "server_name", "modules", "logger", "transaction"] {
                XCTAssertNil(payload[forbidden], "\(forbidden) must not be serialized")
            }

            // A fresh empty scope means no contexts at all; if an SDK release starts attaching
            // defaults, the whitelist still bounds them — so assert the bound, not the absence,
            // and let this test catch whichever world breaks the contract.
            if let contexts = payload["contexts"] as? [String: [String: Any]] {
                for (name, entries) in contexts {
                    XCTAssertNotNil(
                        ContextSentryPolicy.keptContexts[name],
                        "context \(name) is not on the whitelist")
                    for field in entries.keys {
                        XCTAssertTrue(
                            ContextSentryPolicy.keptContexts[name]?.contains(field) ?? false,
                            "context field \(name).\(field) is not on the whitelist")
                    }
                }
            }
        }
    }

    func testHostileEventSerializedPayloadIsScrubbedBeforeSerialization() throws {
        startSDK()

        // A crash-shaped event carrying a leak in every field the whitelist exists to drop —
        // built with the *real SDK types* the crash converter produces, so `beforeSend` and the
        // serializer see exactly what a native crash's converted event would carry.
        let event = Event(level: .fatal)
        event.exceptions = [
            {
                let exception = Exception(
                    value: "index 9 beyond bounds — /Users/alice/notes.txt", type: "NSRangeException")
                let mechanism = Mechanism(type: "crash")
                mechanism.handled = false
                exception.mechanism = mechanism
                return exception
            }()
        ]
        event.threads = [
            {
                let thread = SentryThread(threadId: 0)
                thread.name = "com.apple.main-thread / transcript writer"
                thread.crashed = true
                thread.current = true
                thread.isMain = true
                let frame = Frame()
                frame.instructionAddress = "0x104abc000"
                frame.imageAddress = "0x104a00000"
                frame.symbolAddress = "0x104abc123"
                frame.function = "ContextApp.render(frame:)"
                frame.fileName = "/Users/alice/src/context/Render.swift"
                frame.package = "/Users/alice/src/context"
                frame.vars = ["transcript": "the user's words", "home": "/Users/alice"]
                frame.inApp = true
                thread.stacktrace = Stacktrace(frames: [frame], registers: [:])
                return thread
            }()
        ]
        event.debugMeta = [
            {
                let image = DebugMeta()
                image.uuid = "AB12CD34-0000-0000-0000-000000000000"
                image.type = "macho"
                image.name = "/Applications/Context for Claude.app/Contents/MacOS/ContextApp"
                image.codeFile = "/Users/alice/src/context/.build/release/ContextApp"
                image.imageAddress = "0x104a00000"
                image.imageSize = 1_048_576
                return image
            }()
        ]
        event.user = User(userId: "alice@example.com")
        event.extra = ["transcript": "never", "system_prompt": "never"]
        event.serverName = "Alices-MacBook-Pro.local"
        event.modules = ["ContextApp": "1.2.3"]
        event.fingerprint = ["arbitrary", "fingerprint"]
        event.message = SentryMessage(formatted: "free text with /Users/alice in it")
        event.tags = ["context-for-claude": "context-for-claude", "smuggled": "/Users/alice"]
        event.context = [
            "device": ["name": "Alice's MacBook Pro", "model": "Mac16,1", "arch": "arm64e"],
            "trace": ["trace_id": "0123abcd"],
        ]

        SentrySDK.capture(event: event)

        for payload in try capturedEventPayloads() {
            // Top-level drops — both spellings, since the wire format is snake_case.
            for forbidden in ["user", "breadcrumbs", "extra", "request", "server_name", "servername", "modules", "logger", "transaction"] {
                XCTAssertNil(payload[forbidden], "\(forbidden) must not be serialized")
            }

            // Exception: type survives; the free-text value is gone. (`SentryException.value` is
            // non-null in the SDK's API, so the adapter writes the empty string — asserted as
            // "absent or empty", never text.)
            let exception = try XCTUnwrap(valuesArray(payload, under: "exception").first)
            XCTAssertEqual(exception["type"] as? String, "NSRangeException")
            let serializedValue = exception["value"] as? String
            XCTAssertTrue(
                serializedValue == nil || serializedValue?.isEmpty == true,
                "exception value must not carry free text, got \(serializedValue ?? "nil")")

            // Threads: no names; frames keep symbolication's inputs and drop paths, snippets and
            // captured locals.
            let thread = try XCTUnwrap(valuesArray(payload, under: "threads").first)
            XCTAssertNil(thread["name"], "thread names are arbitrary strings")
            let frame = try XCTUnwrap(
                ((thread["stacktrace"] as? [String: Any])?["frames"] as? [[String: Any]])?.first)
            XCTAssertEqual(frame["instruction_addr"] as? String, "0x104abc000")
            XCTAssertEqual(frame["image_addr"] as? String, "0x104a00000")
            XCTAssertEqual(frame["function"] as? String, "ContextApp.render(frame:)")
            XCTAssertEqual(frame["in_app"] as? Bool, true)
            for forbidden in ["vars", "context_line", "filename", "abs_path", "package", "pre_context", "post_context"] {
                XCTAssertNil(frame[forbidden], "frame field \(forbidden) must not be serialized")
            }

            // Debug images: the UUID symbolication keys on survives; paths on the reporting Mac
            // do not.
            let image = try XCTUnwrap((payload["debugmeta"] as? [String: Any])?["images"] as? [[String: Any]])
                .first
            XCTAssertEqual(image?["uuid"] as? String, "AB12CD34-0000-0000-0000-000000000000")
            XCTAssertEqual(image?["type"] as? String, "macho")
            XCTAssertEqual(image?["image_addr"] as? String, "0x104a00000")
            for forbidden in ["name", "code_file", "codefile"] {
                XCTAssertNil(image?[forbidden], "image field \(forbidden) must not be serialized")
            }

            // Context subfields: device.name (the user's own name for their Mac) is the leak this
            // whitelist exists to drop; an unknown context is gone entirely.
            let contexts = try XCTUnwrap(payload["contexts"] as? [String: [String: Any]])
            XCTAssertEqual(contexts["device"], ["model": "Mac16,1", "arch": "arm64e"])
            XCTAssertNil(contexts["trace"])

            // Tags, fingerprint, message: out-of-vocabulary values do not reach the wire.
            XCTAssertEqual(payload["tags"] as? [String: String], ["context-for-claude": "context-for-claude"])
            XCTAssertNil(payload["fingerprint"], "arbitrary fingerprints are dropped, not forwarded")
            XCTAssertNil(payload["message"], "a free-text message is dropped, not forwarded")

            // …and this traffic crossed the admission gate on its way out.
            XCTAssertEqual(
                ContextSentryGate.recordedAdmissionDecisions().last?.decision,
                .admittedBeforeEntry)
        }
    }

    func testOptionsAssemblyDisablesEveryAutomaticProducer() throws {
        let options = Options()
        SentrySDKReporting.apply(
            ContextSentry.StartOptions(
                dsn: "https://public-key@sentry.invalid/42",
                releaseName: "context-for-claude@0.0.0-test+1",
                dist: "1",
                environment: "production",
                cacheRoot: "/tmp/cfc-sentry-options"),
            to: options)

        // Crash/error diagnostics only. Each of these is a producer of *non-event envelopes or
        // captured content* that `beforeSend` would never see, which is why the option — not a
        // scrub — is the enforcement point.
        XCTAssertTrue(options.enableCrashHandler)
        XCTAssertFalse(options.enableAutoSessionTracking)
        XCTAssertFalse(options.enableAppHangTracking)
        XCTAssertFalse(options.enableAppHangTrackingV2)
        XCTAssertFalse(options.enableWatchdogTerminationTracking)
        XCTAssertFalse(options.enableAutoBreadcrumbTracking)
        XCTAssertEqual(options.maxBreadcrumbs, 0)
        XCTAssertFalse(options.enableAutoPerformanceTracing)
        XCTAssertFalse(options.enableAppLaunchProfiling)
        XCTAssertFalse(options.enableSwizzling)
        XCTAssertFalse(options.enableCaptureFailedRequests)
        XCTAssertFalse(options.attachScreenshot)
        XCTAssertFalse(options.attachViewHierarchy)
        XCTAssertFalse(options.sendDefaultPii)
        XCTAssertFalse(options.sendClientReports)
        XCTAssertFalse(options.enableSpotlight)
        XCTAssertFalse(options.debug)

        // Identity and state routing.
        XCTAssertEqual(options.releaseName, "context-for-claude@0.0.0-test+1")
        XCTAssertEqual(options.dist, "1")
        XCTAssertEqual(options.environment, "production")
        XCTAssertEqual(options.cacheDirectoryPath, "/tmp/cfc-sentry-options")
        let session = try XCTUnwrap(options.urlSession)
        XCTAssertEqual(
            session.configuration.protocolClasses?.first,
            ContextSentryGate.self,
            "every SDK request must cross the admission gate")
    }
}

private extension URLRequest {
    /// `URLProtocol` request copies expose bodies as streams; normalize so tests can read them.
    var bodyData: Data? {
        if let body = httpBody { return body }
        guard let stream = httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let read = stream.read(buffer, maxLength: bufferSize)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }
}
