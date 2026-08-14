import Foundation

enum WorkHistoryHandleKind: String, Codable, Sendable {
  case url
  case file
  case appWindow = "app_window"
}

struct WorkHistoryHandle: Equatable, Hashable, Codable, Sendable {
  var kind: WorkHistoryHandleKind
  var value: String

  var identityKey: String { "\(kind.rawValue)::\(value)" }

  var isDurable: Bool { kind == .url || kind == .file }

  func jsonObject() -> [String: String] {
    ["kind": kind.rawValue, "value": value]
  }

  static func url(_ raw: String) -> WorkHistoryHandle? {
    guard let canonical = canonicalizeURL(raw) else { return nil }
    return WorkHistoryHandle(kind: .url, value: canonical)
  }

  static func file(_ raw: String) -> WorkHistoryHandle? {
    guard let canonical = canonicalizeFile(raw) else { return nil }
    return WorkHistoryHandle(kind: .file, value: canonical)
  }

  static func appWindow(appName: String, title: String) -> WorkHistoryHandle? {
    let app = appName.trimmingCharacters(in: .whitespacesAndNewlines)
    let cleaned = title.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !app.isEmpty, !cleaned.isEmpty else { return nil }
    return WorkHistoryHandle(kind: .appWindow, value: "\(app)\n\(cleaned)")
  }

  static func decodeList(from json: String?) -> [WorkHistoryHandle] {
    guard let json, let data = json.data(using: .utf8),
      let objects = try? JSONDecoder().decode([WorkHistoryHandle].self, from: data)
    else { return [] }
    return objects
  }

  static func encodeList(_ handles: [WorkHistoryHandle]) -> String {
    guard let data = try? JSONEncoder().encode(handles),
      let text = String(data: data, encoding: .utf8)
    else { return "[]" }
    return text
  }

  static func primary(in handles: [WorkHistoryHandle]) -> WorkHistoryHandle? {
    handles.first(where: { $0.isDurable }) ?? handles.first
  }

  static func canonicalizeURL(_ raw: String) -> String? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let url = URL(string: trimmed), let scheme = url.scheme?.lowercased() else { return nil }
    guard scheme == "http" || scheme == "https" else { return nil }
    guard let host = url.host?.lowercased(), !host.isEmpty else { return nil }
    var components = URLComponents()
    components.scheme = scheme
    components.host = host
    if let port = url.port, !((scheme == "http" && port == 80) || (scheme == "https" && port == 443)) {
      components.port = port
    }
    var path = url.path
    if path.count > 1, path.hasSuffix("/") {
      path.removeLast()
    }
    components.percentEncodedPath = path.isEmpty ? "/" : path
    if let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems {
      let kept = items.filter { item in
        let name = item.name.lowercased()
        return !Self.droppedQueryNames.contains(name) && !name.hasPrefix("utm_")
      }
      if !kept.isEmpty {
        components.queryItems = kept
      }
    }
    return components.string
  }

  private static let droppedQueryNames: Set<String> = [
    "usp", "sid", "authuser", "tab", "pli", "hl", "gclid", "fbclid", "igshid",
  ]

  static func canonicalizeFile(_ raw: String) -> String? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }
    let url = URL(fileURLWithPath: trimmed.hasPrefix("file:") ? URL(string: trimmed)?.path ?? trimmed : trimmed)
    let path = url.standardizedFileURL.path
    guard !path.isEmpty, path != "/" else { return nil }
    return path
  }
}

struct WorkHistoryFrontmostSnapshot: Equatable, Sendable {
  var appName: String
  var windowTitle: String?
  var bundleID: String?
  var documentURL: URL?
  var browserURL: URL?
}
