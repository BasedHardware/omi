import Foundation

enum MemorySubjectScope: String, Codable, Sendable {
  case primaryUser = "primary_user"
  case thirdParty = "third_party"
  case artifact
}

enum MemorySubjectEvidence: String, Codable, Sendable {
  case userAuthored = "user_authored"
  case addressedToUser = "addressed_to_user"
  case renderedContent = "rendered_content"
  case uiChrome = "ui_chrome"
}

/// Default-deny admission for screen-derived memories. Missing labels refuse.
enum MemoryAdmissionGate {
  static func admits(_ memory: ExtractedMemory) -> Bool {
    guard let scope = memory.subjectScope,
      let evidence = memory.subjectEvidence,
      let containsCredential = memory.containsCredentialOrIdentifier
    else { return false }
    return scope == .primaryUser
      && (evidence == .userAuthored || evidence == .addressedToUser)
      && !containsCredential
  }
}

/// Label-boundary host match, the same rule ContextCore `DomainPattern` uses.
/// Duplicated here so Desktop does not take a ContextCore dependency.
enum MemoryHostExclusion {
  static func isExcluded(urlString: String?, excludedHosts: Set<String>) -> Bool {
    guard let urlString, let host = normalizeHost(urlString) else { return false }
    return excludedHosts.contains { pattern in
      guard let needle = normalizeHost(pattern) else { return false }
      if host == needle { return true }
      guard host.count > needle.count, host.hasSuffix(needle) else { return false }
      let boundary = host.index(host.endIndex, offsetBy: -(needle.count + 1))
      return host[boundary] == "."
    }
  }

  static func normalizeHost(_ raw: String) -> String? {
    var value = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !value.isEmpty else { return nil }
    if let scheme = value.range(of: "://") {
      value = String(value[scheme.upperBound...])
    } else if value.hasPrefix("//") {
      value = String(value.dropFirst(2))
    }
    if let slash = value.firstIndex(where: { $0 == "/" || $0 == "?" || $0 == "#" }) {
      value = String(value[..<slash])
    }
    if let at = value.firstIndex(of: "@") {
      value = String(value[value.index(after: at)...])
    }
    if value.hasPrefix("[") {
      if let close = value.firstIndex(of: "]") {
        value = String(value[value.index(after: value.startIndex)..<close])
      }
    } else if let colon = value.firstIndex(of: ":") {
      value = String(value[..<colon])
    }
    if value.hasPrefix("www.") { value = String(value.dropFirst(4)) }
    if value.hasSuffix(".") { value.removeLast() }
    return value.isEmpty ? nil : value
  }
}
