import Foundation
import OmiCore
@testable import OmiNetwork
import os
import Testing

/// The token upload sends the body and headers `routers/notifications.py::save_token` reads.
struct NotificationTokenTests {
    @Test func uploadsTokenAndTimeZone() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingProtocol.self]
        let client = try APIClient(
            configuration: AppConfiguration(
                profile: .localDev, apiBaseURL: #require(URL(string: "http://127.0.0.1:8000/")), authEmulator: nil,
                appVersion: "2.0.0", appBuild: "1"
            ),
            tokens: NotificationTestToken(),
            session: URLSession(configuration: configuration)
        )
        try await client.saveNotificationToken("fcm-abc", timeZone: "Europe/Berlin", deviceIDHash: "1a2b3c4d")

        let request = try #require(CapturingProtocol.last.withLock { $0 })
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "http://127.0.0.1:8000/v1/users/fcm-token")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer id-token")
        #expect(request.value(forHTTPHeaderField: "X-App-Platform") == "ios")
        #expect(request.value(forHTTPHeaderField: "X-Device-Id-Hash") == "1a2b3c4d")
        let body = try #require(CapturingProtocol.body.withLock { $0 })
        let json = try #require(JSONSerialization.jsonObject(with: body) as? [String: String])
        #expect(json == ["fcm_token": "fcm-abc", "time_zone": "Europe/Berlin"])
    }
}

private struct NotificationTestToken: AuthTokenProviding {
    func idToken(forceRefresh _: Bool) async throws -> String {
        "id-token"
    }
}

private final class CapturingProtocol: URLProtocol, @unchecked Sendable {
    static let last = OSAllocatedUnfairLock<URLRequest?>(initialState: nil)
    static let body = OSAllocatedUnfairLock<Data?>(initialState: nil)

    override static func canInit(with _: URLRequest) -> Bool {
        true
    }

    override static func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        Self.last.withLock { $0 = request }
        // URLSession moves the body into a stream before the protocol sees it.
        Self.body.withLock { $0 = request.httpBody ?? request.httpBodyStream.map(Self.read) }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"status":"Ok"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    private static func read(_ stream: InputStream) -> Data {
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            guard count > 0 else { break }
            data.append(buffer, count: count)
        }
        return data
    }
}
