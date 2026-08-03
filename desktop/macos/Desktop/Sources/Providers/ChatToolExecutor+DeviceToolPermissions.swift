import AppKit
import Contacts
import EventKit
import Foundation
import Photos

/// Permission request/status handling for the grants only the device tool
/// surface needs. Onboarding never asks for these, so they stay out of
/// `onboardingPermissionTypes` and its status payload.
extension ChatToolExecutor {

  /// TCC statuses, normalized to the vocabulary `check_permission_status`
  /// already returns for the onboarding permissions.
  private static func statusString(granted: Bool, determined: Bool) -> String {
    if !determined { return "not_determined" }
    return granted ? "granted" : "denied"
  }

  static func contactsPermissionStatus() -> String {
    switch CNContactStore.authorizationStatus(for: .contacts) {
    case .authorized: return "granted"
    case .notDetermined: return "not_determined"
    case .restricted: return "restricted"
    case .denied: return "denied"
    @unknown default: return "unknown"
    }
  }

  static func eventKitPermissionStatus(for entityType: EKEntityType) -> String {
    switch EKEventStore.authorizationStatus(for: entityType) {
    case .fullAccess: return "granted"
    case .writeOnly: return "write_only"
    case .notDetermined: return "not_determined"
    case .restricted: return "restricted"
    case .denied: return "denied"
    @unknown default: return "unknown"
    }
  }

  static func photosPermissionStatus() -> String {
    switch PHPhotoLibrary.authorizationStatus(for: .readWrite) {
    case .authorized: return "granted"
    case .limited: return "limited"
    case .notDetermined: return "not_determined"
    case .restricted: return "restricted"
    case .denied: return "denied"
    @unknown default: return "unknown"
    }
  }

  static func deviceToolPermissionStatuses() -> [String: String] {
    [
      "contacts": contactsPermissionStatus(),
      "calendars": eventKitPermissionStatus(for: .event),
      "reminders": eventKitPermissionStatus(for: .reminder),
      "photos": photosPermissionStatus(),
    ]
  }

  private static func requestEventKitAccess(_ entityType: EKEntityType) async -> Bool? {
    await awaitCancellableAsyncRequest {
      let store = EKEventStore()
      do {
        switch entityType {
        case .event: return try await store.requestFullAccessToEvents()
        case .reminder: return try await store.requestFullAccessToReminders()
        @unknown default: return false
        }
      } catch {
        return false
      }
    }
  }

  private static func requestPhotosAccess() async -> Bool? {
    await awaitCancellablePermissionRequest { completion in
      PHPhotoLibrary.requestAuthorization(for: .readWrite) { status in
        completion(status == .authorized || status == .limited)
      }
    }
  }

  /// Handles the device-tool permission types. Each of these has a real system
  /// prompt on first ask; a prior denial can only be undone in System Settings,
  /// which is what the pending message tells the user.
  static func requestDeviceToolPermission(
    _ type: String,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async -> String {
    guard isPermissionAuthorizationCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else {
      return authorizedOwnerChangedResult()
    }

    let granted: Bool?
    let settingsPane: String
    switch type {
    case "contacts":
      if CNContactStore.authorizationStatus(for: .contacts) == .authorized {
        granted = true
      } else {
        granted = await awaitCancellablePermissionRequest { completion in
          Task {
            completion(await ContactsReaderService.requestAccess())
          }
        }
      }
      settingsPane = "Privacy_Contacts"
    case "calendars":
      granted = await requestEventKitAccess(.event)
      settingsPane = "Privacy_Calendars"
    case "reminders":
      granted = await requestEventKitAccess(.reminder)
      settingsPane = "Privacy_Reminders"
    case "photos":
      granted = await requestPhotosAccess()
      settingsPane = "Privacy_Photos"
    default:
      return deviceToolFailure(
        reason: "unknown_permission_type",
        message: "\(type) is not a device tool permission.")
    }

    guard
      let granted,
      isPermissionAuthorizationCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot)
    else { return authorizedOwnerChangedResult() }

    if !granted {
      guard isPermissionAuthorizationCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else {
        return authorizedOwnerChangedResult()
      }
      openPrivacySettingsPane(settingsPane)
    }

    return deviceToolJSON([
      "ok": granted,
      "permission": type,
      "status": granted ? "granted" : "pending",
      "message": granted
        ? "\(type) permission granted."
        : "User needs to enable \(type) for Omi in System Settings > Privacy & Security.",
      "requires_restart": false,
    ])
  }

  private static func openPrivacySettingsPane(_ pane: String) {
    guard
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?\(pane)")
    else { return }
    Task { @MainActor in
      NSWorkspace.shared.open(url)
    }
  }
}
