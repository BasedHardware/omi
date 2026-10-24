import Foundation
@testable import OmiNetwork
import Testing

struct PhoneCallsContractTests {
    /// Flutter `buildPhoneCallWebSocketUrl`: two channels, 48 kHz PCM, the call id the Twilio leg carries.
    @Test func callSocketURLMatchesFlutter() throws {
        let base = try #require(URL(string: "https://api.omi.me/"))
        let url = PhoneCallSocket.url(base: base, uid: "u1", callID: "1759800000000", language: "multi")
        let components = try #require(URLComponents(url: url, resolvingAgainstBaseURL: false))
        #expect(components.scheme == "wss")
        #expect(components.path == "/v4/listen")
        let items = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value ?? "") })
        #expect(items == [
            "source": "phone_call", "call_id": "1759800000000", "uid": "u1", "sample_rate": "48000",
            "codec": "pcm", "language": "multi", "channels": "2",
        ])
        let local = PhoneCallSocket.url(base: try #require(URL(string: "http://127.0.0.1:8000/")), uid: "u", callID: "c", language: "en")
        #expect(local.scheme == "ws")
    }

    /// `verified_at` is Python `isoformat()` with microseconds and an offset.
    @Test func verifiedDatesParse() {
        let micro = APIClient.parsePhoneDate("2026-10-01T10:00:00.123456+00:00")
        let plain = APIClient.parsePhoneDate("2026-10-01T10:00:00+00:00")
        #expect(plain == Date(timeIntervalSince1970: 1_790_848_800))
        #expect(abs((micro ?? .distantPast).timeIntervalSince(plain ?? .distantFuture)) < 1)
        #expect(APIClient.parsePhoneDate("yesterday") == nil)
    }
}
