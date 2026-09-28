import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

import OmiKit

// Windows platform sources. SOURCE-COMPLETE BUT UNBUILT: there is no Swift
// Windows toolchain on this machine, so nothing in this file has compiled.
// It is written against the current OmiKit seams and the Swift-on-Windows
// SDK and must be reviewed as source until the first Windows build.

/// URLSession-backed HTTP plumbing for the Windows host. Foundation's
/// URLSession is supported by the Swift toolchain on Windows (via
/// FoundationNetworking), so no WinRT HTTP stack is needed. Timeouts come
/// from the shared native-core policy through `Policy` — never re-derived.
///
/// Full `BackendTransport` conformance (generation SSE with
/// `Last-Event-ID` resume, software-plane selection, write/recording IDs)
/// lands with the Windows build; this file carries the request plumbing
/// that part plugs into.
struct WindowsTransport: Sendable {
    let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func send(_ request: BackendRequest) async throws -> BackendResponse {
        guard let url = URL(string: request.path) else {
            throw WindowsTransportError.badRequestPath(request.path)
        }
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = request.method.rawValue
        urlRequest.timeoutInterval = TimeInterval(
            Policy.requestTimeoutSeconds(
                method: request.method.rawValue, path: request.path))
        for (field, value) in request.headers {
            urlRequest.setValue(value, forHTTPHeaderField: field)
        }
        if let body = request.body {
            urlRequest.httpBody = Data(body.utf8)
        }

        let (data, response) = try await session.data(for: urlRequest)
        let http = response as? HTTPURLResponse
        let retryAfter = http?.value(forHTTPHeaderField: "Retry-After")
            .flatMap { Int($0) }
        return BackendResponse(
            id: request.id,
            status: http?.statusCode ?? 0,
            body: String(data: data, encoding: .utf8),
            retryAfterSeconds: retryAfter
        )
    }
}

enum WindowsTransportError: Error {
    case badRequestPath(String)
}

/// DPAPI-backed credential storage stub. The implementation wraps
/// CryptProtectData / CryptUnprotectData (dpapi.h, reachable through the
/// WinSDK Swift overlay) with a machine-bound scope and a versioned blob
/// header persisted under %APPDATA%/Omi/credentials. It throws
/// `Unavailable` until the first Windows build wires the C interop and the
/// blob-layout tests that do not run on this machine.
struct WindowsCredentialStore {
    struct Unavailable: Error {}

    func save(_ secret: String, for key: String) throws {
        _ = key
        _ = secret
        throw Unavailable()
    }

    func load(for key: String) throws -> String? {
        _ = key
        throw Unavailable()
    }

    func remove(for key: String) {
        _ = key
    }
}
