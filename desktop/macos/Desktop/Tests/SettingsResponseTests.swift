import XCTest
@testable import Omi_Computer

/// Tests for settings response decoders.
/// Ensures RecordingPermissionResponse and PrivateCloudSyncResponse
/// correctly map backend JSON keys to the Swift `enabled` property.
final class SettingsResponseTests: XCTestCase {

    // MARK: - RecordingPermissionResponse

    func testDecodeRecordingPermissionTrue() throws {
        let json = """
        {"store_recording_permission": true}
        """
        let resp = try JSONDecoder().decode(RecordingPermissionResponse.self, from: json.data(using: .utf8)!)
        XCTAssertTrue(resp.enabled)
    }

    func testDecodeRecordingPermissionFalse() throws {
        let json = """
        {"store_recording_permission": false}
        """
        let resp = try JSONDecoder().decode(RecordingPermissionResponse.self, from: json.data(using: .utf8)!)
        XCTAssertFalse(resp.enabled)
    }

    func testDecodeRecordingPermissionFailsWithWrongKey() {
        let json = """
        {"enabled": true}
        """
        XCTAssertThrowsError(
            try JSONDecoder().decode(RecordingPermissionResponse.self, from: json.data(using: .utf8)!)
        )
    }

    // MARK: - PrivateCloudSyncResponse

    func testDecodePrivateCloudSyncTrue() throws {
        let json = """
        {"private_cloud_sync_enabled": true}
        """
        let resp = try JSONDecoder().decode(PrivateCloudSyncResponse.self, from: json.data(using: .utf8)!)
        XCTAssertTrue(resp.enabled)
    }

    func testDecodePrivateCloudSyncFalse() throws {
        let json = """
        {"private_cloud_sync_enabled": false}
        """
        let resp = try JSONDecoder().decode(PrivateCloudSyncResponse.self, from: json.data(using: .utf8)!)
        XCTAssertFalse(resp.enabled)
    }

    func testDecodePrivateCloudSyncFailsWithWrongKey() {
        let json = """
        {"enabled": false}
        """
        XCTAssertThrowsError(
            try JSONDecoder().decode(PrivateCloudSyncResponse.self, from: json.data(using: .utf8)!)
        )
    }
}
