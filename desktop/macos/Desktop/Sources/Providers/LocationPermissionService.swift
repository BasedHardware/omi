@preconcurrency import CoreLocation
import Foundation

enum LocationPermissionResult {
  case location(CLLocationCoordinate2D)
  case denied
  case unavailable
}

@MainActor
final class LocationPermissionService: NSObject {
  static let shared = LocationPermissionService()

  private let manager = CLLocationManager()
  private let callbackBridge = LocationPermissionDelegate()
  private var authorizationContinuation: CheckedContinuation<CLAuthorizationStatus, Never>?
  private var locationContinuation: CheckedContinuation<LocationPermissionResult, Never>?

  override init() {
    super.init()
    callbackBridge.owner = self
    manager.delegate = callbackBridge
  }

  var isAuthorized: Bool {
    manager.authorizationStatus == .authorizedAlways
  }

  func requestCurrentLocation() async -> LocationPermissionResult {
    let status = manager.authorizationStatus
    let authorization: CLAuthorizationStatus
    if status == .notDetermined {
      authorization = await withCheckedContinuation { continuation in
        authorizationContinuation = continuation
        manager.requestWhenInUseAuthorization()
      }
    } else {
      authorization = status
    }
    guard authorization == .authorizedAlways else { return .denied }
    return await withCheckedContinuation { continuation in
      locationContinuation = continuation
      manager.requestLocation()
    }
  }

  func authorizationChanged(_ status: CLAuthorizationStatus) {
    authorizationContinuation?.resume(returning: status)
    authorizationContinuation = nil
  }

  func received(locations: [CLLocation]) {
    guard let coordinate = locations.last?.coordinate else { return }
    locationContinuation?.resume(returning: .location(coordinate))
    locationContinuation = nil
  }

  func failedLocationRequest() {
    locationContinuation?.resume(returning: .unavailable)
    locationContinuation = nil
  }
}

private final class LocationPermissionDelegate: NSObject, CLLocationManagerDelegate {
  weak var owner: LocationPermissionService?

  func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
    let owner = owner
    Task { @MainActor [weak owner] in
      owner?.authorizationChanged(manager.authorizationStatus)
    }
  }

  func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
    let owner = owner
    Task { @MainActor [weak owner] in
      owner?.received(locations: locations)
    }
  }

  func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
    let owner = owner
    Task { @MainActor [weak owner] in
      owner?.failedLocationRequest()
    }
  }
}
