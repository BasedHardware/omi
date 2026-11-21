import Foundation
import OmiCore
import OmiNetwork

public extension FakeAPIClient {
    /// Like the backend, a sync also marks the integration connected.
    func syncAppleHealth(_ summary: HealthSummary) async throws -> Date? {
        let syncedAt = try lock.withLock {
            if let _error { throw _error }
            if placesAndHealth.failing.contains("healthSync") { throw APIError.http(status: 500, body: "healthSync") }
            placesAndHealth.healthSyncs.append(summary)
            return placesAndHealth.syncedAt
        }
        connectedIntegrations.insert("apple_health")
        return syncedAt
    }

    func markAppleHealthConnected() async throws {
        try lock.withLock {
            if let _error { throw _error }
            if placesAndHealth.failing.contains("healthConnect") { throw APIError.http(status: 500, body: "healthConnect") }
            placesAndHealth.healthMarkedConnected += 1
        }
        connectedIntegrations.insert("apple_health")
    }
}
