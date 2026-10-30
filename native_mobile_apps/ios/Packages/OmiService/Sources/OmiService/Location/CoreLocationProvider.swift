import CoreLocation
import Foundation
import OmiCore

/// `LocationProviding` on CoreLocation: When In Use access, the manager's cached fix, and one
/// `CLLocationUpdate` for a fresh one. Medium accuracy is enough to name a place (and works with
/// "Precise Location" off), as in Flutter.
@MainActor
public final class CoreLocationProvider: NSObject, LocationProviding {
    private let manager = CLLocationManager()
    private var waiting: [CheckedContinuation<LocationAccess, Never>] = []
    /// The status the manager last reported. Reading `authorizationStatus` waits on locationd, which
    /// blocked the app's launch on a white screen, so it is read only until the first report arrives.
    private var reported: CLAuthorizationStatus?

    override public init() {
        super.init()
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        // No status read here: the manager reports it right after this (the delegate below), and
        // that report turns on background fixes.
        manager.delegate = self
    }

    /// A recording can start with the app in the background (the Omi connects, the watch records):
    /// with the `location` background mode and When In Use access, its fix may still be taken there,
    /// as Flutter's geolocator does. Never without the user's permission; Omi never asks for Always.
    private func allowBackgroundFixes() {
        #if os(iOS)
            let modes = Bundle.main.object(forInfoDictionaryKey: "UIBackgroundModes") as? [String] ?? []
            guard modes.contains("location"), access == .allowed else { return }
            manager.allowsBackgroundLocationUpdates = true
            manager.showsBackgroundLocationIndicator = false
        #endif
    }

    public var access: LocationAccess {
        Self.access(reported ?? manager.authorizationStatus)
    }

    public func requestAccess() async -> LocationAccess {
        guard access == .notDetermined else { return access }
        return await withCheckedContinuation { continuation in
            waiting.append(continuation)
            manager.requestWhenInUseAuthorization()
        }
    }

    public func lastKnown() -> GeolocationSnapshot? {
        manager.location.map { Self.snapshot($0, source: .lastKnownPosition) }
    }

    public func currentFix(timeout: Duration) async -> GeolocationSnapshot? {
        guard access == .allowed else { return nil }
        #if os(iOS)
            // Keeps the When In Use grant in effect for this fix if the app is in the background.
            let session = CLServiceSession(authorization: .whenInUse)
            defer { session.invalidate() }
        #endif
        return await withTaskGroup(of: GeolocationSnapshot?.self) { group in
            group.addTask {
                do {
                    for try await update in CLLocationUpdate.liveUpdates(.default) {
                        if let location = update.location { return Self.snapshot(location, source: .currentPosition) }
                    }
                } catch {}
                return nil
            }
            group.addTask {
                try? await Task.sleep(for: timeout)
                return nil
            }
            let first = await group.next() ?? nil
            group.cancelAll()
            return first
        }
    }

    nonisolated static func snapshot(_ location: CLLocation, source: GeolocationSnapshot.Source) -> GeolocationSnapshot {
        GeolocationSnapshot(
            latitude: location.coordinate.latitude, longitude: location.coordinate.longitude,
            altitude: location.verticalAccuracy >= 0 ? location.altitude : nil,
            accuracy: location.horizontalAccuracy >= 0 ? location.horizontalAccuracy : nil,
            capturedAt: location.timestamp, source: source
        )
    }

    nonisolated static func access(_ status: CLAuthorizationStatus) -> LocationAccess {
        switch status {
        case .notDetermined: .notDetermined
        case .authorizedAlways, .authorizedWhenInUse: .allowed
        default: .denied
        }
    }
}

extension CoreLocationProvider: CLLocationManagerDelegate {
    /// Called on the main thread (the manager was made there).
    public nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        let access = Self.access(status)
        MainActor.assumeIsolated { reported = status }
        guard access != .notDetermined else { return }
        MainActor.assumeIsolated {
            allowBackgroundFixes()
            let resumed = waiting
            waiting = []
            resumed.forEach { $0.resume(returning: access) }
        }
    }
}
