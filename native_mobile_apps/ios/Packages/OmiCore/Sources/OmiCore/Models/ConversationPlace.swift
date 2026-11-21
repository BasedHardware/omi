import Foundation

/// Where a conversation happened (backend `models/geolocation.py`, the conversation's `geolocation`).
public struct ConversationLocation: Hashable, Sendable {
    public let latitude: Double
    public let longitude: Double
    /// Reverse-geocoded by the backend; `nil` when geocoding failed or has not run yet.
    public let address: String?
    public let googlePlaceID: String?

    public init(latitude: Double, longitude: Double, address: String? = nil, googlePlaceID: String? = nil) {
        self.latitude = latitude
        self.longitude = longitude
        self.address = address
        self.googlePlaceID = googlePlaceID
    }

    /// Finite and inside the backend's bounds (malformed points are dropped, as Flutter does).
    public var isValid: Bool {
        latitude.isFinite && longitude.isFinite && (-90 ... 90).contains(latitude) && (-180 ... 180).contains(longitude)
    }

    /// Area and city instead of the full street address (Flutter `GetGeolocationWidgets._getShortAddress`):
    /// with three or more comma parts the third- and second-to-last, else the address as is.
    public var shortAddress: String? {
        guard let address = address?.trimmingCharacters(in: .whitespacesAndNewlines), !address.isEmpty else { return nil }
        let parts = address.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
        if parts.count >= 3 { return "\(parts[parts.count - 3]), \(parts[parts.count - 2])" }
        if parts.count == 2 { return "\(parts[0]), \(parts[1])" }
        return address
    }

    /// Great-circle distance in metres.
    public func distance(to other: ConversationLocation) -> Double {
        let radius = 6_371_008.8
        let lat1 = latitude * .pi / 180, lat2 = other.latitude * .pi / 180
        let dLat = lat2 - lat1, dLon = (other.longitude - longitude) * .pi / 180
        let h = sin(dLat / 2) * sin(dLat / 2) + cos(lat1) * cos(lat2) * sin(dLon / 2) * sin(dLon / 2)
        return 2 * radius * asin(min(1, sqrt(h)))
    }
}

/// The position captured when a recording starts, sent with the conversation
/// (`X-Omi-Conversation-Geolocation` on `/v4/listen`) and to `PATCH v1/users/geolocation`.
/// Field names and sources follow Flutter `conversation_location_capture.dart`.
public struct GeolocationSnapshot: Hashable, Sendable {
    public enum Source: String, Sendable {
        case currentPosition = "current_position"
        case lastKnownPosition = "last_known_position"
    }

    public let latitude: Double
    public let longitude: Double
    public let altitude: Double?
    public let accuracy: Double?
    public let capturedAt: Date
    public let source: Source

    public init(latitude: Double, longitude: Double, altitude: Double?, accuracy: Double?, capturedAt: Date, source: Source) {
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.accuracy = accuracy
        self.capturedAt = capturedAt
        self.source = source
    }

    /// Flutter `Geolocation.toJson()`: coordinates, `captured_at` (ISO-8601 UTC) and `capture_source`.
    /// Negative accuracy (CoreLocation's "invalid") and non-finite values are left out; the backend rejects them.
    public var jsonObject: [String: Any] {
        var object: [String: Any] = [
            "latitude": latitude,
            "longitude": longitude,
            "captured_at": Self.iso.string(from: capturedAt),
            "capture_source": source.rawValue,
        ]
        if let accuracy, accuracy.isFinite, accuracy >= 0 { object["accuracy"] = accuracy }
        if let altitude, altitude.isFinite { object["altitude"] = altitude }
        return object
    }

    /// The compact JSON the listen socket carries in its upgrade header.
    public var headerValue: String? {
        guard let data = try? JSONSerialization.data(withJSONObject: jsonObject, options: [.sortedKeys]) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private nonisolated(unsafe) static let iso: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

/// Conversations recorded at one place: points within 100 m of every other member
/// (Flutter `buildConversationMapGroups`).
public struct ConversationPlace: Identifiable, Hashable, Sendable {
    public let location: ConversationLocation
    public let conversations: [Conversation]

    /// Stable whatever order the conversations arrived in.
    public var id: String {
        conversations.map(\.id).sorted().joined(separator: ",")
    }

    public static let clusterDistance = 100.0

    /// Sorted by id before grouping so membership does not depend on paging order; each place is
    /// anchored at its first member. Conversations without a valid location are left out.
    public static func group(_ conversations: [Conversation]) -> [ConversationPlace] {
        let located = conversations
            .compactMap { conversation in conversation.location.flatMap { $0.isValid ? (conversation, $0) : nil } }
            .sorted { $0.0.id < $1.0.id }
        var groups: [(points: [ConversationLocation], members: [Conversation])] = []
        for (conversation, point) in located {
            if let index = groups.firstIndex(where: { group in group.points.allSatisfy { $0.distance(to: point) <= clusterDistance } }) {
                groups[index].points.append(point)
                groups[index].members.append(conversation)
            } else {
                groups.append(([point], [conversation]))
            }
        }
        // The first point anchors the place.
        return groups.map { ConversationPlace(location: $0.points[0], conversations: $0.members) }
    }
}
