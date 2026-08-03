import Contacts
import Flutter
import Foundation
import MessageUI
import UIKit

/// The iOS half of the on-device tool surface.
///
/// iOS has no API for sending a message without the user seeing it, so this
/// service deliberately exposes a *propose* verb rather than a send verb:
/// `proposeMessage` presents `MFMessageComposeViewController` prefilled with the
/// recipient and body, and the system sheet is the approval UI. The result
/// reports what the user actually did, so the caller can record a real outcome
/// instead of assuming delivery — the same contract the macOS surface gets from
/// its approval dispatch.
///
/// Reading messages has no iOS equivalent at all. That capability only exists on
/// the paired Mac.
class DeviceToolsService: NSObject {
  private var pendingComposeResult: FlutterResult?
  private weak var pendingComposeController: MFMessageComposeViewController?

  func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "capabilities":
      result(capabilities())
    case "contactsPermissionStatus":
      // `ok` marks that the status was read, not that access was granted. The
      // common result contract treats a missing `ok` as failure, so omitting it
      // made every successful status check read as one.
      result(["ok": true, "status": contactsPermissionStatus()])
    case "requestContactsPermission":
      requestContactsPermission(result: result)
    case "cancelPendingCompose":
      cancelPendingCompose(result: result)
    case "searchContacts":
      searchContacts(call: call, result: result)
    case "proposeMessage":
      proposeMessage(call: call, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  /// What the agent may attempt on this device. Declaring this explicitly keeps
  /// the model from proposing a send on a device (iPad, iPod touch) that has no
  /// messaging service configured.
  private func capabilities() -> [String: Any] {
    [
      "can_send_text": MFMessageComposeViewController.canSendText(),
      "can_send_attachments": MFMessageComposeViewController.canSendAttachments(),
      "can_send_subject": MFMessageComposeViewController.canSendSubject(),
      "can_read_messages": false,
      "can_run_scripts": false,
      "requires_user_confirmation": true,
    ]
  }

  // MARK: - Contacts

  private func contactsPermissionStatus() -> String {
    // iOS 18 lets the user share a subset of contacts. Lookups still work
    // against that subset, so `limited` is a usable grant, not a denial.
    Self.describe(CNContactStore.authorizationStatus(for: .contacts))
  }

  private static func contactsAccessUsable(_ status: CNAuthorizationStatus) -> Bool {
    if status == .authorized { return true }
    if #available(iOS 18.0, *), status == .limited { return true }
    return false
  }

  private func requestContactsPermission(result: @escaping FlutterResult) {
    Self.requestContactsAccess { status, error in
      let usable = Self.contactsAccessUsable(status)
      if usable {
        result([
          "ok": true,
          "status": Self.describe(status),
          "error": error?.localizedDescription ?? "",
        ])
      } else {
        result(contactsPermissionFailure(status: status, message: error?.localizedDescription))
      }
    }
  }

  /// Prompts for Contacts and reports the resulting authorization status.
  ///
  /// The `granted` boolean alone cannot distinguish full access from the iOS 18
  /// limited grant — both come back `true` — so the status is re-read afterwards
  /// rather than inferred. Reporting `limited` as `granted` would tell the model
  /// it had the whole address book when it can only see a subset.
  private static func requestContactsAccess(
    completion: @escaping (CNAuthorizationStatus, Error?) -> Void
  ) {
    CNContactStore().requestAccess(for: .contacts) { _, error in
      let status = CNContactStore.authorizationStatus(for: .contacts)
      DispatchQueue.main.async { completion(status, error) }
    }
  }

  private static func describe(_ status: CNAuthorizationStatus) -> String {
    switch status {
    case .authorized: return "granted"
    case .notDetermined: return "not_determined"
    case .restricted: return "restricted"
    case .denied: return "denied"
    default:
      if #available(iOS 18.0, *), status == .limited { return "limited" }
      return "unknown"
    }
  }

  private func searchContacts(call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard let args = call.arguments as? [String: Any],
      let query = (args["query"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
      !query.isEmpty
    else {
      result(failure(reason: "missing_query", message: "Provide a name to search for."))
      return
    }
    let limit = min(max((args["limit"] as? Int) ?? 10, 1), 50)

    let status = CNContactStore.authorizationStatus(for: .contacts)
    if status == .notDetermined {
      // The mobile surface exposes only search_contacts and propose_message, so
      // nothing in this flow can call request_permission on the model's behalf.
      // Without prompting here, a fresh install can never resolve a name: the
      // first lookup would report not_determined and every retry would too.
      Self.requestContactsAccess { [weak self] granted, _ in
        guard let self else {
          result(
            Self.failure(
              reason: "surface_unavailable",
              message: "The app closed the tool surface before Contacts access was resolved."))
          return
        }
        guard Self.contactsAccessUsable(granted) else {
          result(self.contactsPermissionFailure(status: granted, message: nil))
          return
        }
        self.searchGrantedContacts(query: query, limit: limit, result: result)
      }
      return
    }
    guard Self.contactsAccessUsable(status) else {
      result(contactsPermissionFailure(status: status, message: nil))
      return
    }
    searchGrantedContacts(query: query, limit: limit, result: result)
  }

  private func searchGrantedContacts(query: String, limit: Int, result: @escaping FlutterResult) {
    let keys: [CNKeyDescriptor] = [
      CNContactFormatter.descriptorForRequiredKeys(for: .fullName),
      CNContactPhoneNumbersKey as CNKeyDescriptor,
      CNContactEmailAddressesKey as CNKeyDescriptor,
    ]

    do {
      let matches = try CNContactStore().unifiedContacts(
        matching: CNContact.predicateForContacts(matchingName: query), keysToFetch: keys)
      let contacts: [[String: Any]] = matches.prefix(limit).map { contact in
        let phones = contact.phoneNumbers.map { entry -> [String: String] in
          [
            "label": entry.label.map { CNLabeledValue<NSString>.localizedString(forLabel: $0) } ?? "",
            "raw_label": entry.label ?? "",
            "value": entry.value.stringValue,
          ]
        }
        let emails = contact.emailAddresses.map { entry -> [String: String] in
          [
            "label": entry.label.map { CNLabeledValue<NSString>.localizedString(forLabel: $0) } ?? "",
            "raw_label": entry.label ?? "",
            "value": entry.value as String,
          ]
        }
        // Matched on the CNLabelPhoneNumber constant, not the localized label:
        // localizedString(forLabel:) returns the user's language, so a substring
        // test for "mobile" only worked on an English device and everywhere else
        // fell through to whatever number came first — often a home or work
        // line. Preparing a message to the wrong number is a real error.
        let preferred =
          phones.first(where: {
            $0["raw_label"] == CNLabelPhoneNumberMobile || $0["raw_label"] == CNLabelPhoneNumberiPhone
          })?["value"]
          ?? phones.first?["value"] ?? emails.first?["value"] ?? ""
        return [
          "id": contact.identifier,
          "name": CNContactFormatter.string(from: contact, style: .fullName) ?? "",
          "phone_numbers": phones,
          "email_addresses": emails,
          "preferred_messaging_handle": preferred,
        ]
      }
      result(["ok": true, "query": query, "count": contacts.count, "contacts": contacts])
    } catch {
      result(failure(reason: "lookup_failed", message: error.localizedDescription))
    }
  }

  // MARK: - Message proposal

  private func proposeMessage(call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard let args = call.arguments as? [String: Any],
      let body = args["text"] as? String,
      !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      result(failure(reason: "empty_body", message: "Provide the message text to propose."))
      return
    }
    let recipients =
      (args["to"] as? [String])?.filter { !$0.isEmpty }
      ?? (args["to"] as? String).map { [$0] }?.filter { !$0.isEmpty }
      ?? []
    guard !recipients.isEmpty else {
      result(failure(reason: "empty_recipient", message: "Provide at least one recipient."))
      return
    }
    guard MFMessageComposeViewController.canSendText() else {
      result(
        failure(
          reason: "messaging_unavailable",
          message: "This device is not configured to send messages."))
      return
    }
    // The overlap check and the reservation both have to happen on the main
    // queue, in that order, without anything in between. Checking here and
    // reserving inside the async block let two calls both observe a nil pending
    // slot, and the second would overwrite the first — stranding a Flutter
    // method call that never gets a reply. `pendingComposeResult` is only ever
    // touched on the main queue for the same reason.
    DispatchQueue.main.async { [weak self] in
      guard let self else {
        result(
          Self.failure(
            reason: "surface_unavailable",
            message: "The app closed the tool surface before the composer opened."))
        return
      }
      guard self.pendingComposeResult == nil else {
        result(
          Self.failure(
            reason: "compose_already_open",
            message: "A message is already awaiting the user's confirmation."))
        return
      }
      guard let presenter = Self.topViewController() else {
        result(
          Self.failure(reason: "no_presenter", message: "The app is not in the foreground."))
        return
      }

      let composer = MFMessageComposeViewController()
      composer.messageComposeDelegate = self
      composer.recipients = recipients
      composer.body = body
      if let subject = args["subject"] as? String, !subject.isEmpty,
        MFMessageComposeViewController.canSendSubject()
      {
        composer.subject = subject
      }

      self.pendingComposeResult = result
      self.pendingComposeController = composer
      presenter.present(composer, animated: true)
    }
  }

  private func cancelPendingCompose(result: @escaping FlutterResult) {
    guard let callback = pendingComposeResult else {
      result(["ok": true, "status": "none"])
      return
    }
    pendingComposeResult = nil
    let composer = pendingComposeController
    pendingComposeController = nil
    composer?.dismiss(animated: true)
    callback(["ok": false, "status": "cancelled"])
    result(["ok": true, "status": "cancelled"])
  }

  private static func topViewController() -> UIViewController? {
    let scene = UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .first { $0.activationState == .foregroundActive }
    guard var top = scene?.windows.first(where: { $0.isKeyWindow })?.rootViewController else {
      return nil
    }
    while let presented = top.presentedViewController {
      top = presented
    }
    return top
  }

  private func failure(reason: String, message: String, permission: String? = nil) -> [String: Any] {
    Self.failure(reason: reason, message: message, permission: permission)
  }

  private func contactsPermissionFailure(status: CNAuthorizationStatus, message: String?) -> [String: Any] {
    let detail = message ?? "Omi needs Contacts access to resolve names to phone numbers."
    guard status == .denied || status == .restricted else {
      return failure(reason: "authorization_denied", message: detail, permission: "contacts")
    }
    let openedSettings: Bool
    if let settingsURL = URL(string: UIApplication.openSettingsURLString) {
      openedSettings = UIApplication.shared.open(settingsURL)
    } else {
      openedSettings = false
    }
    var payload = failure(reason: "authorization_denied", message: "Enable Contacts access in Settings and try again.")
    payload["settings_opened"] = openedSettings
    return payload
  }

  /// The shared failure shape. A permission failure also names the tool that
  /// recovers from it, matching the Dart wrapper and the macOS executors — the
  /// model is told how to fix the problem rather than left to guess.
  private static func failure(
    reason: String, message: String, permission: String? = nil
  ) -> [String: Any] {
    var payload: [String: Any] = ["ok": false, "reason": reason, "error": message]
    if let permission {
      payload["permission"] = permission
      payload["next_tool"] = "request_permission"
      payload["next_tool_arguments"] = ["type": permission]
    }
    return payload
  }
}

extension DeviceToolsService: MFMessageComposeViewControllerDelegate {
  func messageComposeViewController(
    _ controller: MFMessageComposeViewController,
    didFinishWith result: MessageComposeResult
  ) {
    let callback = pendingComposeResult
    pendingComposeResult = nil
    pendingComposeController = nil

    let status: String
    switch result {
    case .sent: status = "sent"
    case .cancelled: status = "cancelled"
    case .failed: status = "failed"
    @unknown default: status = "unknown"
    }

    controller.dismiss(animated: true) {
      // `ok` reflects what the user did, not that the sheet was shown — a
      // cancelled proposal must never read as a delivered message.
      callback?(["ok": status == "sent", "status": status])
    }
  }
}
