import Foundation
@testable import OmiCore
import Testing

struct BackendDateTests {
    @Test func parsesMicrosecondsWithOffset() throws {
        let date = try #require(BackendDate.parse("2026-07-18T20:30:00.123456+00:00"))
        let whole = try #require(BackendDate.parse("2026-07-18T20:30:00Z"))
        #expect(abs(date.timeIntervalSince(whole) - 0.123) < 0.0005)
    }

    @Test func parsesZuluWithoutFraction() {
        #expect(BackendDate.parse("2026-07-18T20:30:00Z") != nil)
    }

    @Test func parsesNaiveAsUTC() {
        #expect(BackendDate.parse("2026-07-18T20:30:00.5") == BackendDate.parse("2026-07-18T20:30:00.5Z"))
    }

    @Test func rejectsGarbage() {
        #expect(BackendDate.parse("yesterday") == nil)
        #expect(BackendDate.parse(nil) == nil)
    }
}

struct AppConfigurationTests {
    @Test func readsLocalDevPlist() {
        let config = AppConfiguration.fromInfoDictionary([
            "OmiAPIScheme": "http", "OmiAPIHost": "127.0.0.1:8000",
            "OmiAppProfile": "local_dev", "OmiAuthEmulatorHost": "127.0.0.1:9099",
        ])
        #expect(config.apiBaseURL.absoluteString == "http://127.0.0.1:8000/")
        #expect(config.profile == .localDev)
        #expect(config.authEmulator?.port == 9099)
    }

    @Test func defaultsToProduction() {
        let config = AppConfiguration.fromInfoDictionary([:])
        #expect(config.apiBaseURL.absoluteString == "https://api.omi.me/")
        #expect(config.authEmulator == nil)
    }
}
