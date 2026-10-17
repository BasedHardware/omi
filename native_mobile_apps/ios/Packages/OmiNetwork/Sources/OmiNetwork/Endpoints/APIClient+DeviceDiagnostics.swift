import Foundation

public extension APIClient {
    /// `POST v1/mobile/device-diagnostics` with `{"bundle_base64": …}` (Flutter `_sendToSupport`).
    /// The backend answers 201 with a 12-character ticket support looks the bundle up by.
    func uploadDeviceDiagnostics(_ bundle: Data) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: ["bundle_base64": bundle.base64EncodedString()])
        let data = try await data(.post, "v1/mobile/device-diagnostics", body: .json(body))
        return try Self.diagnosticsTicket(from: data)
    }
}

extension APIClient {
    static func diagnosticsTicket(from data: Data) throws -> String {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let ticket = object["ticket"] as? String, !ticket.isEmpty
        else { throw APIError.decoding("device-diagnostics: no ticket") }
        return ticket
    }
}
