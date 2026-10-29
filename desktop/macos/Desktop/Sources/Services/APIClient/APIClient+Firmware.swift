import Foundation

struct FirmwareVersionResponse: Decodable {
  let version: String?
  let minVersion: String?
  let minAppVersion: String?
  let minAppVersionCode: String?
  let zipUrl: String?
  let draft: Bool
  let otaUpdateSteps: [String]
  let isLegacySecureDfu: Bool

  enum CodingKeys: String, CodingKey {
    case version
    case minVersion = "min_version"
    case minAppVersion = "min_app_version"
    case minAppVersionCode = "min_app_version_code"
    case zipUrl = "zip_url"
    case draft
    case otaUpdateSteps = "ota_update_steps"
    case isLegacySecureDfu = "is_legacy_secure_dfu"
  }
}

extension APIClient {
  func checkFirmwareUpdate(
    modelNumber: String,
    currentFirmware: String,
    hardwareRevision: String,
    manufacturerName: String
  ) async throws -> FirmwareVersionResponse {
    let queryItems = [
      URLQueryItem(name: "device_model", value: modelNumber),
      URLQueryItem(name: "firmware_revision", value: currentFirmware),
      URLQueryItem(name: "hardware_revision", value: hardwareRevision),
      URLQueryItem(name: "manufacturer_name", value: manufacturerName),
    ]
    return try await get("v2/firmware/latest", queryItems: queryItems)
  }
}
