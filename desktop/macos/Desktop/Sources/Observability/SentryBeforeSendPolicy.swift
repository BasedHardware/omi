import Foundation

extension AppDelegate {
  static func shouldDropSentryEvent(
    isUserReport: Bool,
    isDev: Bool,
    urlTag: String?,
    messageFormatted: String?,
    exceptions: [(type: String, value: String)]
  ) -> Bool {
    if isUserReport { return false }
    if isDev { return true }
    if messageFormatted?.trimmingCharacters(in: .whitespacesAndNewlines)
      .caseInsensitiveCompare("Session Heartbeat") == .orderedSame
    {
      return true
    }
    if let urlTag,
      urlTag.contains("localhost") || urlTag.contains("127.0.0.1")
        || urlTag.contains("trycloudflare.com")
    {
      return true
    }
    let transientNetworkCodes: [(domain: String, codes: [String])] = [
      ("NSURLErrorDomain", ["-999", "-1001", "-1003", "-1004", "-1005", "-1009", "-1011", "-1020"]),
      ("NSPOSIXErrorDomain", ["54", "57", "89"]),
    ]
    if exceptions.contains(where: { exception in
      transientNetworkCodes.contains { entry in
        exception.type == entry.domain
          && entry.codes.contains {
            exception.value.contains("Code=\($0)") || exception.value.contains("Code: \($0)")
          }
      }
    }) {
      return true
    }
    if let lower = messageFormatted?.lowercased(),
      lower.contains("api key expired") || lower.contains("renew the api key")
        || lower.contains("api_key_invalid")
        || lower.contains("ai service authentication error")
        || lower.contains("invalid_auth")
    {
      return true
    }
    if exceptions.contains(where: {
      $0.type == "Omi_Computer.AuthError" && $0.value.contains("notSignedIn")
    }) {
      return true
    }
    return false
  }
}
