import XCTest

@testable import OmiKit

/// The legacy sign-in browser leg: the authorize URL shape the native
/// module sends (the old `/v1/auth/google` default 404s upstream), the
/// callback shape check for both redirect kinds, and the stamped-origin
/// allowlist (`v5BackendOrigin.ts`).
final class AuthSessionTests: XCTestCase {
    // MARK: legacyAuthorizeURL

    func testAuthorizeURLMirrorsNativeQuery() throws {
        let url = try XCTUnwrap(
            legacyAuthorizeURL(
                base: "https://api.omi.me/v1/auth/authorize",
                redirectURI: "http://127.0.0.1:19500/callback",
                state: "st-123",
                codeChallenge: "challenge-abc"))
        let components = try XCTUnwrap(URLComponents(string: url))
        XCTAssertEqual(components.scheme, "https")
        XCTAssertEqual(components.host, "api.omi.me")
        XCTAssertEqual(components.path, "/v1/auth/authorize")
        let values = Dictionary(
            uniqueKeysWithValues: (components.queryItems ?? []).compactMap { item in
                item.value.map { (item.name, $0) }
            })
        XCTAssertEqual(
            values,
            [
                "provider": "google",
                "redirect_uri": "http://127.0.0.1:19500/callback",
                "state": "st-123",
                "code_challenge": "challenge-abc",
                "code_challenge_method": "S256",
            ])
    }

    func testAuthorizeURLEncodesLoopbackRedirect() throws {
        let url = try XCTUnwrap(
            legacyAuthorizeURL(
                base: "https://api.omi.me/v1/auth/authorize",
                redirectURI: "http://127.0.0.1:8123/callback",
                state: "s",
                codeChallenge: "c"))
        // URLComponents encodes query values minimally (like the native
        // module's NSURLQueryItems): `:` and `/` are legal in a query.
        XCTAssertEqual(
            url,
            "https://api.omi.me/v1/auth/authorize?provider=google&redirect_uri"
                + "=http://127.0.0.1:8123/callback&state=s&code_challenge=c"
                + "&code_challenge_method=S256")
    }

    // MARK: authCallbackCode

    func testLoopbackCallbackYieldsCode() {
        let redirect = "http://127.0.0.1:19500/callback"
        XCTAssertEqual(
            authCallbackCode(
                "http://127.0.0.1:19500/callback?code=xyz&state=st",
                redirectURI: redirect,
                expectedState: "st"),
            "xyz")
    }

    func testValidGoogleProviderCallbacksRemainAcceptedForBothRedirects() {
        let callbacks = [
            (
                "http://127.0.0.1:19500/callback?code=loopback%2Bcode&state=st",
                "http://127.0.0.1:19500/callback", "loopback+code"
            ),
            (
                "omi-rnruntime://auth/callback?code=app-code&state=st"
                    + "&scope=email%20profile&authuser=0&prompt=consent",
                "omi-rnruntime://auth/callback", "app-code"
            ),
        ]

        for (callback, redirect, expectedCode) in callbacks {
            XCTAssertEqual(
                authCallbackCode(callback, redirectURI: redirect, expectedState: "st"),
                expectedCode)
        }
    }

    func testLoopbackHeaderAccumulatorWaitsForSplitCallbackHeaders() {
        var accumulator = AuthHTTPRequestHeaderAccumulator()

        XCTAssertEqual(
            accumulator.append(Data("GET /callback?code=provider-code&".utf8)),
            .incomplete)
        XCTAssertEqual(
            accumulator.append(Data("state=st HTTP/1.1\r\nHost: 127.0.0.1\r\n".utf8)),
            .incomplete)
        XCTAssertEqual(
            accumulator.append(Data("\r\n".utf8)),
            .complete(
                "GET /callback?code=provider-code&state=st HTTP/1.1\r\n"
                    + "Host: 127.0.0.1\r\n\r\n"))
    }

    func testLoopbackHeaderAccumulatorRejectsOversizedAndInvalidHeaders() {
        var accumulator = AuthHTTPRequestHeaderAccumulator(maximumBytes: 16)
        XCTAssertEqual(accumulator.append(Data(repeating: 65, count: 16)), .tooLarge)

        var invalidUTF8 = AuthHTTPRequestHeaderAccumulator()
        XCTAssertEqual(
            invalidUTF8.append(Data([0xFF, 0x0D, 0x0A, 0x0D, 0x0A])),
            .invalidEncoding)
    }

    func testLoopbackCallbackDecodesCodeAndRejectsUserInfo() {
        let redirect = "http://127.0.0.1:19500/callback"
        XCTAssertEqual(
            authCallbackCode(
                "\(redirect)?code=a%2Bb%2F%3D&state=st",
                redirectURI: redirect,
                expectedState: "st"),
            "a+b/=")
        XCTAssertNil(
            authCallbackCode(
                "http://user@127.0.0.1:19500/callback?code=x&state=st",
                redirectURI: redirect,
                expectedState: "st"))
    }

    func testAppSchemeCallbackYieldsCode() {
        let redirect = "omi-rnruntime://auth/callback"
        XCTAssertEqual(
            authCallbackCode(
                "omi-rnruntime://auth/callback?code=a1&state=s2",
                redirectURI: redirect,
                expectedState: "s2"),
            "a1")
    }

    @MainActor
    func testBrowserAuthStartFailureFinishesWithoutWaitingForCallback() async {
        let result = await startBrowserAuthSession { _ in false }

        XCTAssertNil(result)
    }

    @MainActor
    func testBrowserAuthCallbackIsReturnedWhenStartSucceeds() async {
        let callback = "omi-rnruntime://auth/callback?code=provider&state=expected"
        let result = await startBrowserAuthSession { finish in
            finish(callback)
            return true
        }

        XCTAssertEqual(result, callback)
    }

    @MainActor
    func testBrowserAuthSynchronousCompletionBeforeFailedStartIsOneShot() async {
        let callback = "omi-rnruntime://auth/callback?code=provider&state=expected"
        let result = await startBrowserAuthSession { finish in
            finish(callback)
            return false
        }

        XCTAssertEqual(result, callback)
    }

    @MainActor
    func testBrowserAuthFailedStartIgnoresLateCompletion() async {
        let recorder = AuthCallbackRecorder()
        let result = await startBrowserAuthSession { finish in
            recorder.handler = finish
            return false
        }

        XCTAssertNil(result)
        recorder.handler?("late callback")
    }

    func testStartingNewBrowserAttemptRetiresOlderCallbackGeneration() {
        var generations = BrowserAuthSessionGeneration()
        let first = generations.beginAttempt()

        XCTAssertTrue(generations.isCurrent(first))

        let second = generations.beginAttempt()

        XCTAssertFalse(generations.isCurrent(first))
        XCTAssertTrue(generations.isCurrent(second))
    }

    func testCallbackRejections() {
        let loopback = "http://127.0.0.1:19500/callback"
        // State mismatch.
        XCTAssertNil(
            authCallbackCode(
                "http://127.0.0.1:19500/callback?code=xyz&state=other",
                redirectURI: loopback,
                expectedState: "st"))
        // Missing code.
        XCTAssertNil(
            authCallbackCode(
                "http://127.0.0.1:19500/callback?state=st",
                redirectURI: loopback,
                expectedState: "st"))
        // Fragment smuggling.
        XCTAssertNil(
            authCallbackCode(
                "http://127.0.0.1:19500/callback?code=x&state=st#frag",
                redirectURI: loopback,
                expectedState: "st"))
        // Wrong port (unbound listener).
        XCTAssertNil(
            authCallbackCode(
                "http://127.0.0.1:19999/callback?code=x&state=st",
                redirectURI: loopback,
                expectedState: "st"))
        // Scheme swap on the app-scheme redirect.
        XCTAssertNil(
            authCallbackCode(
                "https://auth/callback?code=x&state=st",
                redirectURI: "omi-rnruntime://auth/callback",
                expectedState: "st"))
        // Malformed callback.
        XCTAssertNil(
            authCallbackCode(
                "not a url", redirectURI: loopback, expectedState: "st"))
    }

    func testCallbackRejectsDuplicateAndValuelessQueryKeys() {
        let redirect = "omi-rnruntime://auth/callback"
        for query in [
            "code=x&code=y&state=st",
            "code=x&state=st&state=st",
            "code=x&state=st&%73tate=other",
            "code=x&state=st&state",
            "code=x&state=st&extra=a&extra=b",
            "code=x&state=st&extra",
        ] {
            XCTAssertNil(
                authCallbackCode(
                    "\(redirect)?\(query)", redirectURI: redirect, expectedState: "st"),
                query)
        }
    }

    func testCallbackRejectsUserInfoErrorsEncodedPathAndEmptyState() {
        let redirect = "omi-rnruntime://auth/callback"
        for callback in [
            "omi-rnruntime://auth/%63allback?code=x&state=st",
            "omi-rnruntime://user@auth/callback?code=x&state=st",
            "omi-rnruntime://user:password@auth/callback?code=x&state=st",
            "\(redirect)?code=x&state=st&error=access_denied",
            "\(redirect)?code=x&state=st&error=",
        ] {
            XCTAssertNil(authCallbackCode(callback, redirectURI: redirect, expectedState: "st"))
        }
        XCTAssertNil(
            authCallbackCode("\(redirect)?code=x&state=", redirectURI: redirect, expectedState: ""))
    }

    // MARK: isAllowedV5Hostname (v5BackendOrigin.ts)

    func testAllowedV5Hostnames() {
        XCTAssertTrue(isAllowedV5Hostname("127.0.0.1"))
        XCTAssertTrue(isAllowedV5Hostname("localhost"))
        XCTAssertTrue(isAllowedV5Hostname("::1"))
        XCTAssertTrue(isAllowedV5Hostname("api.omi.me"))
        XCTAssertTrue(isAllowedV5Hostname("omi-v5-backend-staging.example.workers.dev"))
        XCTAssertFalse(isAllowedV5Hostname("workers.dev"))
        XCTAssertFalse(isAllowedV5Hostname("evil.dev"))
        // Shared-provider Cloud Run suffixes stay rejected.
        XCTAssertFalse(isAllowedV5Hostname("something.run.app"))
    }
}

@MainActor
private final class AuthCallbackRecorder {
    var handler: (@MainActor @Sendable (String?) -> Void)?
}
