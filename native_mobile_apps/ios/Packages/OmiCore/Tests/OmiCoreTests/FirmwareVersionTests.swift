import Foundation
@testable import OmiCore
import Testing

struct FirmwareVersionTests {
    @Test func parsesLikeTheBackend() {
        #expect(FirmwareVersion("v3.0.21")?.parts == [3, 0, 21])
        #expect(FirmwareVersion("3.0")?.parts == [3, 0, 0])
        #expect(FirmwareVersion(" 2.0.10 ")?.parts == [2, 0, 10])
        #expect(FirmwareVersion("") == nil)
        #expect(FirmwareVersion(nil) == nil)
        #expect(FirmwareVersion("Unknown") == nil)
        #expect(FirmwareVersion("3.0.x") == nil)
        #expect(FirmwareVersion("3..1") == nil)
    }

    @Test func comparesNumerically() throws {
        let older = try #require(FirmwareVersion("3.0.9"))
        let newer = try #require(FirmwareVersion("3.0.10"))
        #expect(older < newer)
        #expect(try #require(FirmwareVersion("3.0")) == #require(FirmwareVersion("v3.0.0")))
        #expect(try #require(FirmwareVersion("3.1")) > #require(FirmwareVersion("3.0.99")))
        #expect(try #require(FirmwareVersion("3.0.0.1")) > #require(FirmwareVersion("3.0")))
    }

    @Test func offersOnlyNewerMcubootReleases() throws {
        let url = try #require(URL(string: "https://example.com/ota.zip"))
        let release = FirmwareRelease(version: "3.0.22", minVersion: "3.0.6", zipURL: url, isLegacySecureDFU: false, notes: nil)
        #expect(release.isUpdate(from: "3.0.21"))
        #expect(!release.isUpdate(from: "3.0.22"))
        #expect(!release.isUpdate(from: "3.1.0"))
        // Below the minimum, or an unreadable current version: never offered.
        #expect(!release.isUpdate(from: "3.0.5"))
        #expect(!release.isUpdate(from: nil))
        #expect(!release.isUpdate(from: "Unknown"))
        let legacy = FirmwareRelease(version: "2.0.11", minVersion: nil, zipURL: url, isLegacySecureDFU: true, notes: nil)
        #expect(!legacy.isUpdate(from: "2.0.10"))
    }
}
