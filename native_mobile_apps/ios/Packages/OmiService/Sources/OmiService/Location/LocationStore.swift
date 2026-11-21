import Foundation
import Observation
import OmiCore
import OmiNetwork

/// Location access as the app shows it (When In Use only; Omi never asks for Always).
public enum LocationAccess: Sendable, Equatable {
    case notDetermined, allowed, denied
}

/// The device's location, behind a seam so the store's rules test without CoreLocation.
@MainActor
public protocol LocationProviding: AnyObject {
    var access: LocationAccess { get }
    /// Shows the system prompt (When In Use) and returns the answer.
    func requestAccess() async -> LocationAccess
    /// The OS's last fix, if any (instant).
    func lastKnown() -> GeolocationSnapshot?
    /// A fresh fix, or `nil` after `timeout`.
    func currentFix(timeout: Duration) async -> GeolocationSnapshot?
}

/// Where a recording starts (Flutter `ConversationLocationCapture`): the position travels with the
/// conversation (`X-Omi-Conversation-Geolocation`) and, best effort, to the user-location cache.
/// Location is metadata: it never holds up recording for long and every failure just means "no place".
@MainActor
@Observable
public final class LocationStore {
    public private(set) var access: LocationAccess

    /// A last-known fix up to this old is used instead of waiting for a fresh one.
    static let lastKnownMaxAge: TimeInterval = 5 * 60
    static let fixTimeout = Duration.seconds(2)

    private let provider: any LocationProviding
    private let api: any APIClientProtocol
    private let now: () -> Date

    public init(provider: any LocationProviding, api: any APIClientProtocol, now: @escaping () -> Date = Date.init) {
        self.provider = provider
        self.api = api
        self.now = now
        access = provider.access
    }

    /// The system may have changed it (Settings app, "Allow Once" expiring).
    public func refresh() {
        access = provider.access
    }

    /// Onboarding and Settings › Data & Privacy.
    public func requestAccess() async {
        access = await provider.requestAccess()
    }

    /// The recording's location. Never asked here: the permission is asked in onboarding's
    /// permissions step or Settings › Privacy, never as a surprise prompt mid-flow (a recording runs
    /// during onboarding too). Without access the recording simply goes without a place.
    public func snapshotForRecording() async -> GeolocationSnapshot? {
        refresh()
        switch access {
        case .notDetermined, .denied:
            return nil
        case .allowed:
            break
        }
        let snapshot: GeolocationSnapshot? = if let last = provider.lastKnown(), isFresh(last) {
            last
        } else {
            await provider.currentFix(timeout: Self.fixTimeout)
        }
        if let snapshot {
            let api = api
            Task { try? await api.updateUserGeolocation(snapshot) }
        }
        return snapshot
    }

    private func isFresh(_ snapshot: GeolocationSnapshot) -> Bool {
        let age = now().timeIntervalSince(snapshot.capturedAt)
        return age >= 0 && age <= Self.lastKnownMaxAge
    }
}
