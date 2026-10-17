import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

/// Answers every request with a canned response and keeps the last request.
final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var response: (status: Int, body: String) = (202, "{}")
    nonisolated(unsafe) static var lastRequest: URLRequest?
    nonisolated(unsafe) static var lastBody: Data?

    override static func canInit(with _: URLRequest) -> Bool {
        true
    }

    override static func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        Self.lastRequest = request
        Self.lastBody = request.httpBody ?? request.httpBodyStream.map(Self.read)
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.response.status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.response.body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    static func read(_ stream: InputStream) -> Data {
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            guard count > 0 else { break }
            data.append(buffer, count: count)
        }
        return data
    }
}

struct StaticToken: AuthTokenProviding {
    func idToken(forceRefresh _: Bool) async throws -> String {
        "token-1"
    }
}

/// Serialized: the stub's request log is shared.
@Suite(.serialized)
struct SyncUploadTests {
    func client() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        let app = AppConfiguration(
            profile: .localDev, apiBaseURL: URL(string: "http://127.0.0.1:8000/")!,
            authEmulator: nil, appVersion: "1.0", appBuild: "1"
        )
        return APIClient(configuration: app, tokens: StaticToken(), session: URLSession(configuration: configuration))
    }

    @Test func uploadIsOneMultipartFilesPart() async throws {
        StubURLProtocol.response = (202, #"{"job_id":"j1","status":"queued","total_files":1,"total_segments":0,"poll_after_ms":2000}"#)
        let name = "audio_6f1d0c3a_opus_fs320_16000_1_fs320_1760000000.bin"
        let frame = Data([80, 0, 0, 0]) + Data(repeating: 0xA0, count: 80)
        let upload = try await client().uploadOfflineRecording(filename: name, data: frame)
        #expect(upload == SyncUpload(jobID: "j1", status: "queued"))

        let request = try #require(StubURLProtocol.lastRequest)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "http://127.0.0.1:8000/v2/sync-local-files")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer token-1")
        #expect(request.value(forHTTPHeaderField: "X-App-Platform") == "ios")
        let type = try #require(request.value(forHTTPHeaderField: "Content-Type"))
        #expect(type.hasPrefix("multipart/form-data; boundary="))
        let body = try #require(StubURLProtocol.lastBody)
        let text = try #require(String(bytes: body, encoding: .isoLatin1))
        #expect(text.contains(#"Content-Disposition: form-data; name="files"; filename="\#(name)""#))
        #expect(text.contains("Content-Type: application/octet-stream"))
        #expect(body.range(of: frame) != nil)
    }

    @Test func synchronousResultCountsAsCompleted() async throws {
        StubURLProtocol.response = (200, #"{"new_memories":[],"updated_memories":[]}"#)
        let upload = try await client().uploadOfflineRecording(filename: "audio_x_opus_16000_1_fs160_1760000000.bin", data: Data([1]))
        #expect(upload == SyncUpload(jobID: nil, status: "completed"))
    }

    @Test func jobStatusAndExpiredJob() async throws {
        StubURLProtocol.response = (200, #"{"job_id":"j1","status":"failed","reason_code":"stt_invalid_input"}"#)
        let job = try #require(try await client().syncJob(id: "j1"))
        #expect(StubURLProtocol.lastRequest?.url?.path == "/v2/sync-local-files/j1")
        #expect(job.isFinished && job.isPermanentFailure)
        StubURLProtocol.response = (404, #"{"detail":"not found"}"#)
        #expect(try await client().syncJob(id: "gone") == nil)
    }

    @Test func refusedUploadSurfacesTheStatus() async {
        StubURLProtocol.response = (422, #"{"code":"backfill_lookback_exceeded"}"#)
        await #expect(throws: APIError.self) {
            _ = try await client().uploadOfflineRecording(filename: "a_1.bin", data: Data([1]))
        }
    }
}
