import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
final class FakeLocation: LocationProviding {
    var access: LocationAccess
    var last: GeolocationSnapshot?
    var fresh: GeolocationSnapshot?
    var answer: LocationAccess = .allowed
    private(set) var prompts = 0
    private(set) var fixRequests = 0

    init(access: LocationAccess) {
        self.access = access
    }

    func requestAccess() async -> LocationAccess {
        prompts += 1
        access = answer
        return answer
    }

    func lastKnown() -> GeolocationSnapshot? {
        last
    }

    func currentFix(timeout _: Duration) async -> GeolocationSnapshot? {
        fixRequests += 1
        return fresh
    }
}

@MainActor
struct LocationStoreTests {
    static let now = Date(timeIntervalSince1970: 1_791_400_000)

    static func fix(minutesAgo: Double, _ source: GeolocationSnapshot.Source) -> GeolocationSnapshot {
        GeolocationSnapshot(
            latitude: 52.52, longitude: 13.405, altitude: 34, accuracy: 12,
            capturedAt: now.addingTimeInterval(-minutesAgo * 60), source: source
        )
    }

    func settle(until condition: () -> Bool) async throws {
        for _ in 0 ..< 400 where !condition() {
            try await Task.sleep(for: .milliseconds(5))
        }
    }

    @Test func aFreshLastKnownFixIsUsedAtOnce() async throws {
        let api = FakeAPIClient()
        let provider = FakeLocation(access: .allowed)
        provider.last = Self.fix(minutesAgo: 2, .lastKnownPosition)
        let store = LocationStore(provider: provider, api: api, now: { Self.now })
        let snapshot = await store.snapshotForRecording()
        #expect(snapshot?.source == .lastKnownPosition)
        #expect(provider.fixRequests == 0)
        // The compatibility cache hears about it too, best effort.
        try await settle { api.placesAndHealth.userGeolocations.count == 1 }
        #expect(api.placesAndHealth.userGeolocations == [snapshot].compactMap(\.self))
    }

    @Test func aStaleLastKnownFixWaitsForAFreshOne() async {
        let provider = FakeLocation(access: .allowed)
        provider.last = Self.fix(minutesAgo: 30, .lastKnownPosition)
        provider.fresh = Self.fix(minutesAgo: 0, .currentPosition)
        let store = LocationStore(provider: provider, api: FakeAPIClient(), now: { Self.now })
        #expect(await store.snapshotForRecording()?.source == .currentPosition)
        #expect(provider.fixRequests == 1)
    }

    /// The permission is asked in onboarding and Settings only, never as a surprise mid-recording.
    @Test func neverAskedGivesNoPlaceAndNoPrompt() async throws {
        let provider = FakeLocation(access: .notDetermined)
        let store = LocationStore(provider: provider, api: FakeAPIClient(), now: { Self.now })
        #expect(await store.snapshotForRecording() == nil)
        try await Task.sleep(for: .milliseconds(50))
        #expect(provider.prompts == 0)
        #expect(store.access == .notDetermined)
    }

    @Test func deniedGivesNoPlaceAndNoPrompt() async {
        let api = FakeAPIClient()
        let provider = FakeLocation(access: .denied)
        provider.last = Self.fix(minutesAgo: 1, .lastKnownPosition)
        let store = LocationStore(provider: provider, api: api, now: { Self.now })
        #expect(await store.snapshotForRecording() == nil)
        #expect(provider.prompts == 0)
        #expect(api.placesAndHealth.userGeolocations.isEmpty)
    }

    @Test func recordingCarriesTheLocationOnTheListenSocket() async {
        let api = FakeAPIClient()
        let capture = CaptureStore(
            api: api, engine: FakePhoneEngine(), deviceEngine: FakeDeviceTranscription(), preferences: freshPreferences(),
            defaultOnDevice: false, userID: { "alice" }
        )
        let place = Self.fix(minutesAgo: 1, .lastKnownPosition)
        capture.recordingLocation = { place }
        await capture.startPhone()
        #expect(api.listenOptions.last?.geolocation == place)
        await capture.stop()
    }
}

final class FakeHealthReader: HealthDataReading, @unchecked Sendable {
    var isAvailable = true
    var shown = true
    var readable = true
    var summary: HealthSummary? = {
        var summary = HealthSummary(periodDays: 7)
        summary.dailySteps = [.init(date: "2026-10-07", dateMs: 1_791_331_200_000, steps: 8400)]
        return summary
    }()

    private(set) var requests = 0

    func requestAuthorization() async -> Bool {
        requests += 1
        return shown
    }

    func probeAccess() async -> Bool {
        readable
    }

    func summary(days _: Int) async -> HealthSummary? {
        summary
    }
}

@MainActor
struct AppleHealthStoreTests {
    func make(_ api: FakeAPIClient, _ reader: FakeHealthReader, now: Date = LocationStoreTests.now) -> AppleHealthStore {
        AppleHealthStore(api: api, reader: reader, preferences: freshPreferences(), now: { now })
    }

    @Test func connectSyncsThenMarksConnected() async {
        let api = FakeAPIClient()
        let store = make(api, FakeHealthReader())
        await store.connect()
        #expect(store.isConnected)
        #expect(store.notice == .connected)
        #expect(api.placesAndHealth.healthSyncs.map(\.totalSteps) == [8400])
        #expect(api.placesAndHealth.healthMarkedConnected == 1)
        #expect(store.lastSync == api.placesAndHealth.syncedAt)
    }

    @Test func nothingReadableIsADenial() async {
        let api = FakeAPIClient()
        let reader = FakeHealthReader()
        reader.readable = false
        let store = make(api, reader)
        await store.connect()
        #expect(!store.isConnected)
        #expect(store.notice == .denied)
        #expect(api.placesAndHealth.healthSyncs.isEmpty)
    }

    @Test func unavailableNeverPrompts() async {
        let reader = FakeHealthReader()
        reader.isAvailable = false
        let store = make(FakeAPIClient(), reader)
        await store.connect()
        #expect(store.notice == .unavailable)
        #expect(reader.requests == 0)
    }

    @Test func disconnectDeletesTheIntegration() async {
        let api = FakeAPIClient()
        let store = make(api, FakeHealthReader())
        await store.connect()
        await store.disconnect()
        #expect(!store.isConnected)
        #expect(store.notice == .disconnected)
        #expect(!api.connectedIntegrations.contains("apple_health"))
    }

    @Test func returningToTheAppSyncsAtMostHourly() async {
        let api = FakeAPIClient()
        api.connectedIntegrations.insert("apple_health")
        let store = make(api, FakeHealthReader())
        await store.syncIfConnected()
        await store.syncIfConnected()
        #expect(api.placesAndHealth.healthSyncs.count == 1)
        #expect(store.isConnected)
    }

    @Test func syncBodyUsesTheBackendFields() {
        var summary = HealthSummary(periodDays: 7)
        summary.dailySteps = [.init(date: "2026-10-07", dateMs: 1, steps: 7000)]
        summary.heartRate = .init(average: 64, minimum: 50, maximum: nil)
        let body = summary.syncBody
        #expect(body["total_steps"] as? Int == 7000)
        #expect(body["average_steps_per_day"] as? Int == 1000)
        #expect(body["heart_rate_average"] as? Double == 64)
        #expect(body["heart_rate_max"] == nil)
        #expect((body["daily_steps"] as? [[String: Any]])?.first?["dateMs"] as? Double == 1)
        #expect(JSONSerialization.isValidJSONObject(body))
    }
}
