@testable import ContextApp
import Foundation
import XCTest

/// The canned backing protocol the gate forwards into during tests: records every request it is
/// handed and answers from a per-test closure. Real `URLSession` machinery drives everything
/// around it. The cancellation test additionally drives a protocol instance directly to place
/// stopLoading at a deterministic point during task preparation.
final class CannedForwarder: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, [String: String], Data))?
    private static let requestLock = NSLock()
    private static var requests: [URLRequest] = []
    static var receivedRequests: [URLRequest] { requestLock.withLock { requests } }

    static func reset() {
        handler = nil
        requestLock.withLock { requests = [] }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let request = Self.requestWithoutStream(self.request)
        Self.requestLock.withLock { Self.requests.append(request) }
        guard let handler = Self.handler, let client else {
            client?.urlProtocol(
                self,
                didFailWithError: NSError(
                    domain: NSURLErrorDomain, code: NSURLErrorBadServerResponse))
            return
        }
        let (status, headers, body) = handler(request)
        let response = HTTPURLResponse(
            url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!
        client.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client.urlProtocol(self, didLoad: body)
        client.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    /// `URLProtocol` request copies expose bodies as streams; normalize so assertions see URLs,
    /// headers, and bodies uniformly.
    private static func requestWithoutStream(_ request: URLRequest) -> URLRequest {
        var normalized = request
        if normalized.httpBody == nil, let stream = normalized.httpBodyStream {
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
            normalized.httpBodyStream = nil
            normalized.httpBody = data
        }
        return normalized
    }
}

/// Admission-gate behavior exercised through the real gated `URLSession`.
///
/// The one-way entry flag is process-global by design, so every test here models a **fresh
/// process**: `setUp` resets the real flag and every seam via
/// `ContextSentryGate.resetTestSeams()`, injects what the test needs, and `tearDown` resets
/// again — the same discipline the lifecycle suites use between modeled processes. Tests drive
/// the production entry point (`enterAirgap()`) and the production flag (`isClosed`); there is no
/// override for the entry state.
final class ContextSentryGateTests: XCTestCase {
    private var backingSession: URLSession?

    override func setUp() {
        super.setUp()
        ContextSentryGate.resetTestSeams()
        ContextSentryGate.liveSuppression = { false }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CannedForwarder.self]
        let session = URLSession(
            configuration: configuration,
            delegate: ContextSentryGate.RedirectFollowerStopper(), delegateQueue: nil)
        backingSession = session
        ContextSentryGate.forwarderOverride = { _ in session }
        CannedForwarder.reset()
    }

    override func tearDown() {
        backingSession?.invalidateAndCancel()
        backingSession = nil
        ContextSentryGate.resetTestSeams()
        CannedForwarder.reset()
        super.tearDown()
    }

    private func get(_ url: URL) throws -> (data: Data, response: HTTPURLResponse) {
        let session = ContextSentryGate.makeSentrySession()
        defer { session.invalidateAndCancel() }
        let expectation = expectation(description: "request finished")
        var result: Result<(Data, URLResponse), Error>?
        let task = session.dataTask(with: url) { data, response, error in
            if let error { result = .failure(error) }
            else { result = .success((data ?? Data(), response!)) }
            expectation.fulfill()
        }
        task.resume()
        wait(for: [expectation], timeout: 5)

        let settled = try XCTUnwrap(result)
        switch settled {
        case .failure(let error): throw error
        case .success(let pair):
            return (pair.0, try XCTUnwrap(pair.1 as? HTTPURLResponse))
        }
    }

    private func awaitFailure(_ request: URLRequest) throws -> NSError {
        let session = ContextSentryGate.makeSentrySession()
        defer { session.invalidateAndCancel() }
        let expectation = expectation(description: "request failed")
        var error: Error?
        let task = session.dataTask(with: request) { _, _, taskError in
            error = taskError
            expectation.fulfill()
        }
        task.resume()
        wait(for: [expectation], timeout: 5)
        return try XCTUnwrap(error as NSError?, "the request was expected to fail")
    }

    func testAdmissionBeforeEntrySendsAndDelivers() throws {
        CannedForwarder.handler = { _ in (200, [:], Data("ok".utf8)) }

        let outcome = try get(URL(string: "https://sentry.invalid/api/42/envelope/")!)

        XCTAssertEqual(outcome.response.statusCode, 200)
        XCTAssertEqual(outcome.data, Data("ok".utf8))
        let decisions = ContextSentryGate.recordedAdmissionDecisions()
        XCTAssertEqual(decisions.count, 1)
        XCTAssertEqual(decisions[0].decision, .admittedBeforeEntry)
    }

    func testLiveSuppressionRefusesWithoutClosingTheGate() throws {
        ContextSentryGate.liveSuppression = { true }
        CannedForwarder.handler = { _ in (200, [:], Data()) }

        _ = try awaitFailure(
            URLRequest(url: URL(string: "https://sentry.invalid/api/42/envelope/")!))

        XCTAssertEqual(
            ContextSentryGate.recordedAdmissionDecisions().first?.decision,
            .refusedByLiveSuppression)
        // The refusal is *not* an Airgap entry: the flag is untouched, so a subsequent policy
        // change re-opens reporting without a relaunch.
        XCTAssertFalse(ContextSentryGate.isClosed)
        // And nothing reached the backing session.
        XCTAssertTrue(CannedForwarder.receivedRequests.isEmpty)
    }

    /// Entry during task preparation must precede the final locked admission check.
    func testEntryDuringAdmissionRefusesAndNeverForwards() throws {
        let factory = try XCTUnwrap(ContextSentryGate.forwarderOverride)
        ContextSentryGate.forwarderOverride = { configuration in
            ContextSentryGate.enterAirgap()
            return factory(configuration)
        }
        CannedForwarder.handler = { _ in
            XCTFail("the backing session must never see a request admitted across entry")
            return (200, [:], Data("ok".utf8))
        }

        let failure = try awaitFailure(
            URLRequest(url: URL(string: "https://sentry.invalid/api/42/envelope/")!))

        XCTAssertEqual(
            ContextSentryGate.recordedAdmissionDecisions().first?.decision,
            .refusedAfterEntry,
            "the entry check runs after task preparation, under the admission lock")
        XCTAssertEqual(
            failure.domain, NSURLErrorDomain, "the refusal is an error to the sender, not silence")
        XCTAssertTrue(CannedForwarder.receivedRequests.isEmpty)
        XCTAssertTrue(ContextSentryGate.isClosed)
    }

    func testStopDuringTaskPreparationPreventsResume() throws {
        let gate = ContextSentryGate(
            request: URLRequest(url: URL(string: "https://sentry.invalid/api/42/envelope/")!),
            cachedResponse: nil, client: nil)
        let factory = try XCTUnwrap(ContextSentryGate.forwarderOverride)
        ContextSentryGate.forwarderOverride = { configuration in
            gate.stopLoading()
            return factory(configuration)
        }
        gate.startLoading()
        XCTAssertEqual(ContextSentryGate.recordedAdmissionDecisions().last?.decision,
                       .cancelledBeforeAdmission)
        XCTAssertTrue(CannedForwarder.receivedRequests.isEmpty)
    }

    /// Redirects are refused outright: the send fails with the 3xx, and the redirect target is
    /// never contacted — by the gate, and not by the backing session either, whose delegate veto
    /// is what turns the 3xx into the final response here.
    func testRedirectIsRefusedAndTargetNeverContacted() throws {
        CannedForwarder.handler = { request in
            if request.url?.host == "sentry.invalid" {
                return (302, ["Location": "https://other.invalid/collect"], Data())
            }
            XCTFail("the redirect target must never be contacted")
            return (200, [:], Data("landed".utf8))
        }

        var request = URLRequest(url: URL(string: "https://sentry.invalid/api/42/envelope/")!)
        request.httpMethod = "POST"
        request.setValue("https://sentry.invalid", forHTTPHeaderField: "X-Sentry-Auth")
        request.setValue("application/x-sentry-envelope", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data("envelope-bytes".utf8)

        let failure = try awaitFailure(request)

        XCTAssertEqual(
            failure.code, NSURLErrorBadServerResponse, "a 3xx is a failed send, not a follow")

        // Exactly one request reached the backing session — the original, with its envelope body
        // intact through the real URLProtocol stream plumbing. No redirected request was issued
        // anywhere.
        XCTAssertEqual(CannedForwarder.receivedRequests.count, 1)
        let forwarded = try XCTUnwrap(CannedForwarder.receivedRequests.first)
        XCTAssertEqual(forwarded.url?.host, "sentry.invalid")
        XCTAssertEqual(forwarded.httpMethod, "POST")
        XCTAssertEqual(forwarded.httpBody, Data("envelope-bytes".utf8))
    }

    func testRedirectFollowerStopperRefusesEveryRedirect() {
        // The forwarder session's delegate is what stops a bare URLSession from following a
        // redirect behind the gate's back. Its veto is the documented `completionHandler(nil)`;
        // the 3xx then reaches the gate's completion handler, which fails the send.
        let stopper = ContextSentryGate.RedirectFollowerStopper()
        let expectation = expectation(description: "redirect decision made")
        var vetoed: URLRequest? = URLRequest(url: URL(string: "https://other.invalid/x")!)
        let session = URLSession(configuration: .ephemeral)
        let task = session.dataTask(with: URL(string: "https://sentry.invalid/x")!)
        stopper.urlSession(
            session, task: task,
            willPerformHTTPRedirection: HTTPURLResponse(
                url: URL(string: "https://sentry.invalid/x")!, statusCode: 302,
                httpVersion: "HTTP/1.1", headerFields: ["Location": "https://other.invalid/x"])!,
            newRequest: URLRequest(url: URL(string: "https://other.invalid/x")!)
        ) { request in
            vetoed = request
            expectation.fulfill()
        }
        wait(for: [expectation], timeout: 5)
        task.cancel()
        session.finishTasksAndInvalidate()
        XCTAssertNil(vetoed, "nil means 'do not follow'; the 3xx becomes a refused send")
    }

    func testEntryFlagIsOneWayUntilAResetModelsAFreshProcess() {
        XCTAssertFalse(ContextSentryGate.isClosed)

        ContextSentryGate.enterAirgap()
        XCTAssertTrue(ContextSentryGate.isClosed)
        ContextSentryGate.enterAirgap()  // idempotent
        XCTAssertTrue(ContextSentryGate.isClosed)

        // `resetTestSeams` is the modeled fresh process — the only thing that returns the flag to
        // open, and how the suites bound one modeled process from the next.
        ContextSentryGate.resetTestSeams()
        XCTAssertFalse(ContextSentryGate.isClosed)
    }
}
