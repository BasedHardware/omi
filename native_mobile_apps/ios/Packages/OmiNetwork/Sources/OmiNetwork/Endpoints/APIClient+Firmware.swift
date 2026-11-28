import Foundation
import OmiCore

public extension APIClient {
    /// `GET v2/firmware/latest` (`backend/routers/firmware.py`). The backend answers 404 when there
    /// is nothing newer for this device, which is `nil` here, not an error.
    func latestFirmware(model: String, firmware: String, hardware: String?, manufacturer: String?) async throws -> FirmwareRelease? {
        let query = [
            URLQueryItem(name: "device_model", value: model),
            URLQueryItem(name: "firmware_revision", value: firmware),
            // Required by the endpoint, unused by it; the Flutter app sends "Unknown" too.
            URLQueryItem(name: "hardware_revision", value: hardware ?? "Unknown"),
            URLQueryItem(name: "manufacturer_name", value: manufacturer ?? "Unknown"),
        ]
        let data: Data
        do {
            data = try await self.data(.get, "v2/firmware/latest", query: query)
        } catch let APIError.http(status, _) where status == 404 {
            return nil
        }
        return try FirmwareReleaseMapper.release(from: decode(FirmwareReleaseDTO.self, from: data))
    }
}

/// The wire shape of `FirmwareVersionResponse`.
struct FirmwareReleaseDTO: Decodable {
    enum Changelog: Decodable {
        case text(String)
        case lines([String])

        init(from decoder: any Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let lines = try? container.decode([String].self) {
                self = .lines(lines)
            } else {
                self = try .text(container.decode(String.self))
            }
        }
    }

    let version: String?
    let min_version: String?
    let zip_url: String?
    let draft: Bool?
    let is_legacy_secure_dfu: Bool?
    let changelog: Changelog?
}

enum FirmwareReleaseMapper {
    /// `nil` for a draft or a response without a version or download.
    static func release(from dto: FirmwareReleaseDTO) -> FirmwareRelease? {
        guard dto.draft != true, let version = dto.version, !version.isEmpty,
              let zip = dto.zip_url, let url = URL(string: zip) else { return nil }
        return FirmwareRelease(
            version: version,
            minVersion: dto.min_version,
            zipURL: url,
            // The backend defaults to true; only an explicit false means MCUboot over SMP.
            isLegacySecureDFU: dto.is_legacy_secure_dfu ?? true,
            notes: notes(dto.changelog)
        )
    }

    private static func notes(_ changelog: FirmwareReleaseDTO.Changelog?) -> String? {
        let lines: [String] = switch changelog {
        case let .text(text): text.split(whereSeparator: \.isNewline).map(String.init)
        case let .lines(lines): lines
        case nil: []
        }
        let cleaned = lines
            .map { $0.trimmingCharacters(in: .whitespaces.union(CharacterSet(charactersIn: "-*•"))) }
            .filter { !$0.isEmpty }
        guard let first = cleaned.first else { return nil }
        return first.prefix(1).uppercased() + first.dropFirst()
    }
}
