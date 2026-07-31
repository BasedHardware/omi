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

  func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "capabilities":
      result(capabilities())
    case "contactsPermissionStatus":
      result(["status": contactsPermissionStatus()])
    case "requestContactsPermission":
      requestContactsPermission(result: result)
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
    switch CNContactStore.authorizationStatus(for: .contacts) {
    case .authorized: return "granted"
    case .notDetermined: return "not_determined"
    case .restricted: return "restricted"
    case .denied: return "denied"
    default:
      // iOS 18 lets the user share a subset of contacts. Lookups still work
      // against that subset, so this is a usable grant, not a denial.
      if #available(iOS 18.0, *), CNContactStore.authorizationStatus(for: .contacts) == .limited {
        return "limited"
      }
      return "unknown"
    }
  }

  private static func contactsAccessUsable(_ status: CNAuthorizationStatus) -> Bool {
    if status == .authorized { return true }
    if #available(iOS 18.0, *), status == .limited { return true }
    return false
  }

  private func requestContactsPermission(result: @escaping FlutterResult) {
    CNContactStore().requestAccess(for: .contacts) { granted, error in
      DispatchQueue.main.async {
        result([
          "ok": granted,
          "status": granted ? "granted" : "denied",
          "error": error?.localizedDescription ?? "",
        ])
      }
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
    guard Self.contactsAccessUsable(status) else {
      result(
        failure(
          reason: status == .notDetermined ? "not_determined" : "authorization_denied",
          message: "Omi needs Contacts access to resolve names to phone numbers.",
          permission: "contacts"))
      return
    }

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
            "value": entry.value.stringValue,
          ]
        }
        let emails = contact.emailAddresses.map { entry -> [String: String] in
          [
            "label": entry.label.map { CNLabeledValue<NSString>.localizedString(forLabel: $0) } ?? "",
            "value": entry.value as String,
          ]
        }
        let preferred =
          phones.first(where: { $0["label"]?.localizedCaseInsensitiveContains("mobile") == true })?["value"]
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
    let recipients = (args["to"] as? [String])?.filter { !$0.isEmpty }
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
    // One sheet at a time: a second proposal while the user is still deciding
    // would replace the first and strand its result callback.
    guard pendingComposeResult == nil else {
      result(
        failure(
          reason: "compose_already_open",
          message: "A message is already awaiting the user's confirmation."))
      return
    }

    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      guard let presenter = Self.topViewController() else {
        result(
          failure(reason: "no_presenter", message: "The app is not in the foreground."))
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
      presenter.present(composer, animated: true)
    }
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
    var payload: [String: Any] = ["ok": false, "reason": reason, "error": message]
    if let permission {
      payload["permission"] = permission
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
