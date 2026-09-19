@testable import ContextApp
import Foundation
import XCTest

/// The canned backing protocol the gate forwards into during tests: records every request it is
/// handed and answers from a per-test closure. Real `URLSession` machinery drives everything
/// around it — the gated session issues requests, `urlProtocol(wasRedirectedTo:)` re-issues
/// redirects through `ContextSentryGate.startLoading` — so no test here calls the admission
/// function by hand.
final class CannedForwarder: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, [String: String], Data))?
    nonisolated(unsafe) static var receivedRequests: [URLRequest] = []

    static func reset() {
        handler = nil
        receivedRequests = []
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let request = Self.requestWithoutStream(self.request)
        Self.receivedRequests.append(request)
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
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    /// `URLProtocol` request copies expose bodies as streams; normalize so assertions see URLs
    /// and headers uniformly.
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
            normalized.httpBody = data
            normalized.httpBodyStream = nil
        }
        return normalized
    }
}

/// Admission-gate behavior, proven through the real gated `URLSession`.
///
/// The one-way entry flag is process-global by design; every test here pins
/// `ContextSentryGate.entryOverride` in `setUp` and clears it in `tearDown`, so no test can leave
/// the gate open or closed for another suite. The single test of the *real* flag is named to sort
/// last in this class, because once it runs, `enterAirgap()` has done what it says.
final class ContextSentryGateTests: XCTestCase {

    override func setUp() {
        super.setUp()
        ContextSentryGate.entryOverride = false
        ContextSentryGate.liveSuppression = { false }
        ContextSentryGate.forwarderOverride = { configuration in
            configuration.protocolClasses = [CannedForwarder.self]
            return URLSession(configuration: configuration)
        }
        CannedForwarder.reset()
    }

    override func tearDown() {
        ContextSentryGate.resetTestSeams()
        CannedForwarder.reset()
        super.tearDown()
    }

    private func get(_ url: URL) throws -> (data: Data, response: HTTPURLResponse) {
        let session = ContextSentryGate.makeSentrySession()
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

        do {
            _ = try get(URL(string: "https://sentry.invalid/api/42/envelope/")!)
            XCTFail("suppressed request must not be delivered")
        } catch {
            // Expected: the gate refuses with a connectivity-style error.
        }

        XCTAssertEqual(
            ContextSentryGate.recordedAdmissionDecisions().first?.decision,
            .refusedByLiveSuppression)
        // The refusal is *not* an Airgap entry: the sticky flag is untouched, so a subsequent
        // policy change re-opens reporting without a relaunch.
        XCTAssertFalse(ContextSentryGate.isClosed)
        // And nothing reached the backing session.
        XCTAssertTrue(CannedForwarder.receivedRequests.isEmpty)
    }

    func testQueuedRedirectCrossingEntryIsRefused() throws {
        // The Airgap switch lands *between* the original send and its redirect hop: the canned
        // handler closes the gate exactly when the first request is forwarded. The redirected
        // request is then a queued request arriving after entry.
        CannedForwarder.handler = { request in
            if request.url?.host == "sentry.invalid" {
                ContextSentryGate.entryOverride = true  // entry, mid-flight
                return (302, ["Location": "https://sentry.invalid/moved"], Data())
            }
            XCTFail("the redirect hop must never reach the backing session after entry")
            return (200, [:], Data())
        }

        do {
            _ = try get(URL(string: "https://sentry.invalid/api/42/envelope/")!)
            XCTFail("a queued redirect must not complete after entry")
        } catch {
            // Expected.
        }

        let decisions = ContextSentryGate.recordedAdmissionDecisions()
        XCTAssertEqual(decisions.count, 2, "original admitted, redirect evaluated and refused")
        XCTAssertEqual(decisions[0].decision, .admittedBeforeEntry)
        XCTAssertEqual(decisions[0].url.host, "sentry.invalid")
        XCTAssertEqual(decisions[1].decision, .refusedAfterEntry)
        XCTAssertEqual(decisions[1].url.path, "/moved")
        // Only the original reached the backing session.
        XCTAssertEqual(CannedForwarder.receivedRequests.count, 1)
    }

    func testRedirectIsReAdmittedThroughTheGateWithSanitizedHeaders() throws {
        // Cross-host redirect: the hop must re-cross admission (second recorded decision) and
        // arrive at the backing session stripped of everything — the URL survives, no header does.
        CannedForwarder.handler = { request in
            if request.url?.host == "sentry.invalid" {
                return (302, ["Location": "https://other.invalid/collect"], Data())
            }
            return (200, [:], Data("landed".utf8))
        }

        var request = URLRequest(url: URL(string: "https://sentry.invalid/api/42/envelope/")!)
        request.httpMethod = "POST"
        request.setValue("https://sentry.invalid", forHTTPHeaderField: "X-Sentry-Auth")
        request.setValue("Bearer dsn-key", forHTTPHeaderField: "Authorization")
        request.setValue("application/x-sentry-envelope", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data("envelope-bytes".utf8)

        let session = ContextSentryGate.makeSentrySession()
        let expectation = expectation(description: "redirect finished")
        var finalData: Data?
        var finalResponse: HTTPURLResponse?
        let task = session.dataTask(with: request) { data, response, _ in
            finalData = data
            finalResponse = response as? HTTPURLResponse
            expectation.fulfill()
        }
        task.resume()
        wait(for: [expectation], timeout: 5)

        XCTAssertEqual(finalResponse?.statusCode, 200)
        XCTAssertEqual(finalData, Data("landed".utf8))

        // Two admissions: the original and the redirected hop — through URLSession's real
        // redirect machinery, not a second hand call.
        let decisions = ContextSentryGate.recordedAdmissionDecisions()
        XCTAssertEqual(decisions.count, 2)
        XCTAssertEqual(decisions[0].decision, .admittedBeforeEntry)
        XCTAssertEqual(decisions[1].decision, .admittedBeforeEntry)
        XCTAssertEqual(decisions[1].url.absoluteString, "https://other.invalid/collect")

        // The hop reached the backing session downgraded to GET, bodyless, and headerless:
        // cross-host strips everything, auth-ish headers never cross a redirect.
        let hop = try XCTUnwrap(CannedForwarder.receivedRequests.last)
        XCTAssertEqual(hop.url?.host, "other.invalid")
        XCTAssertEqual(hop.httpMethod, "GET")
        XCTAssertNil(hop.httpBody)
        XCTAssertEqual(hop.allHTTPHeaderFields ?? [:], [:])
    }

    func testSameHostRedirectKeepsHeadersButNotAuth() throws {
        CannedForwarder.handler = { request in
            if request.url?.path == "/api/42/envelope/" {
                return (307, ["Location": "https://sentry.invalid/api/42/envelope/retry"], Data())
            }
            return (200, [:], Data("ok".utf8))
        }

        var request = URLRequest(url: URL(string: "https://sentry.invalid/api/42/envelope/")!)
        request.httpMethod = "POST"
        request.setValue("application/x-sentry-envelope", forHTTPHeaderField: "Content-Type")
        request.setValue("https://sentry.invalid", forHTTPHeaderField: "X-Sentry-Auth")
        request.httpBody = Data("envelope-bytes".utf8)

        _ = try get(from: request)

        let hop = try XCTUnwrap(CannedForwarder.receivedRequests.last)
        XCTAssertEqual(hop.url?.path, "/api/42/envelope/retry")
        XCTAssertEqual(hop.httpMethod, "POST", "307 same-host keeps method")
        XCTAssertEqual(hop.httpBody, Data("envelope-bytes".utf8), "307 same-host keeps body")
        XCTAssertEqual(hop.value(forHTTPHeaderField: "Content-Type"), "application/x-sentry-envelope")
        XCTAssertNil(hop.value(forHTTPHeaderField: "X-Sentry-Auth"), "DSN auth never crosses a redirect")
    }

    private func get(from request: URLRequest) throws -> HTTPURLResponse {
        let session = ContextSentryGate.makeSentrySession()
        let expectation = expectation(description: "request finished")
        var response: HTTPURLResponse?
        let task = session.dataTask(with: request) { _, urlResponse, _ in
            response = urlResponse as? HTTPURLResponse
            expectation.fulfill()
        }
        task.resume()
        wait(for: [expectation], timeout: 5)
        return try XCTUnwrap(response)
    }

    func testRedirectFollowerStopperRefusesEveryRedirect() {
        // The forwarder session's delegate is what stops a bare URLSession from following a
        // redirect behind the gate's back. Its veto is the documented `completionHandler(nil)`.
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
        XCTAssertNil(vetoed, "nil means 'do not follow'; the gate re-admits the hop instead")
    }

    /// Sorts last on purpose: it arms the *real* process-global flag, which cannot be un-set.
    func ztestRealEntryFlagIsOneWayAndPermanent() {
        ContextSentryGate.entryOverride = nil
        XCTAssertFalse(ContextSentryGate.isClosed)

        ContextSentryGate.enterAirgap()
        XCTAssertTrue(ContextSentryGate.isClosed)

        // Idempotent, and permanently closed: a later permitted launch re-arms reporting by being
        // a fresh process, never by reopening this gate.
        ContextSentryGate.enterAirgap()
        XCTAssertTrue(ContextSentryGate.isClosed)
        XCTAssertTrue(ContextSentryGate.hasProcessEnteredAirgapForTests())
    }
}
