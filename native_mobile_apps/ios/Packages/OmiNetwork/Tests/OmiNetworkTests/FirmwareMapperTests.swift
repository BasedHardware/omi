import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct FirmwareMapperTests {
    /// `GET https://api.omi.me/v2/firmware/latest?device_model=Omi%20CV%201&firmware_revision=3.0.10&…` (2026-10-07).
    static let production = """
    {"version":"3.0.21","min_version":"3.0.6","min_app_version":"1.0.74","min_app_version_code":"438",
     "zip_url":"https://github.com/BasedHardware/omi/releases/download/Omi_CV1_v3.0.21/Omi_CV1_OTA_v3.0.21.zip",
     "draft":false,"ota_update_steps":["battery","internet"],"is_legacy_secure_dfu":false,"changelog":["fix audio sync issue"]}
    """

    func map(_ json: String) throws -> FirmwareRelease? {
        try FirmwareReleaseMapper.release(from: JSONDecoder().decode(FirmwareReleaseDTO.self, from: Data(json.utf8)))
    }

    @Test func mapsTheProductionResponse() throws {
        let release = try #require(try map(Self.production))
        #expect(release.version == "3.0.21")
        #expect(release.minVersion == "3.0.6")
        #expect(release.zipURL.lastPathComponent == "Omi_CV1_OTA_v3.0.21.zip")
        #expect(!release.isLegacySecureDFU)
        #expect(release.notes == "Fix audio sync issue")
    }

    @Test func changelogAsTextKeepsTheFirstLine() throws {
        let json = #"{"version":"3.0.22","zip_url":"https://x.test/a.zip","changelog":"- Better battery\n- Fixes"}"#
        #expect(try map(json)?.notes == "Better battery")
        let empty = #"{"version":"3.0.22","zip_url":"https://x.test/a.zip","changelog":""}"#
        #expect(try map(empty)?.notes == nil)
    }

    @Test func missingDfuFlagMeansLegacyLikeTheBackendDefault() throws {
        let json = #"{"version":"2.0.11","zip_url":"https://x.test/a.zip"}"#
        #expect(try map(json)?.isLegacySecureDFU == true)
    }

    @Test func draftsAndEmptyAnswersAreNoRelease() throws {
        #expect(try map(#"{"version":"3.0.22","zip_url":"https://x.test/a.zip","draft":true}"#) == nil)
        #expect(try map(#"{"version":null,"zip_url":null}"#) == nil)
    }
}
