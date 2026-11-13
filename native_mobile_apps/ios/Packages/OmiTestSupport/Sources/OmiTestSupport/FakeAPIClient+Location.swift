import Foundation
import OmiCore
import OmiNetwork

/// Backend state for location, Apple Health and the in-progress conversation.
public final class FakePlacesAndHealth: @unchecked Sendable {
    /// Every `PATCH v1/users/geolocation`, in order.
    public internal(set) var userGeolocations: [GeolocationSnapshot] = []
    /// Every Apple Health summary synced, in order.
    public internal(set) var healthSyncs: [HealthSummary] = []
    public internal(set) var healthMarkedConnected = 0
    public var syncedAt = Date(timeIntervalSince1970: 1_791_400_000)
    /// `GET v1/conversations?statuses=in_progress`.
    public var inProgressConversationID: String?
    public internal(set) var inProgressLookups = 0
    /// Fails just these calls: `geolocation`, `healthSync`, `healthConnect`, `inProgress`.
    public var failing: Set<String> = []

    public init() {}
}

public extension FakeAPIClient {
    private func placesCall(_ name: String, _ body: (FakePlacesAndHealth) -> Void) throws {
        try lock.withLock {
            if let _error { throw _error }
            if placesAndHealth.failing.contains(name) { throw APIError.http(status: 500, body: name) }
            body(placesAndHealth)
        }
    }

    func updateUserGeolocation(_ snapshot: GeolocationSnapshot) async throws {
        try placesCall("geolocation") { $0.userGeolocations.append(snapshot) }
    }

    func inProgressConversationID() async throws -> String? {
        try placesCall("inProgress") { $0.inProgressLookups += 1 }
        return lock.withLock { placesAndHealth.inProgressConversationID }
    }
}

public extension FakeLiveChannel {
    func sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: [String]) {
        let entry = "\(speakerID.map(String.init) ?? "-"):\(personID):\(personName):\(segmentIDs.joined(separator: ","))"
        lock.withLock { speakerAssignments.append(entry) }
    }
}
