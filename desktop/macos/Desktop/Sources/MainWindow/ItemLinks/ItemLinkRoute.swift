import Foundation

/// The kinds of record an item link can name. The raw values are the wire
/// keys of the shared item-list link contract (`/items?conversation=…&task=…`)
/// and the host of the singular `<scheme>://<kind>/<id>` links.
enum ItemLinkKind: String, CaseIterable, Sendable {
  case conversation
  case task
  case memory
}

/// One record named by a link. Carries only the kind and id: the contract
/// puts no titles or other content in the URL.
struct ItemLinkReference: Hashable, Sendable {
  let kind: ItemLinkKind
  let id: String
}

/// What an incoming app-scheme URL asks the main window to show.
enum ItemLinkRoute: Equatable, Sendable {
  /// `<scheme>://conversation/<id>` (and task/memory): open that detail.
  case single(ItemLinkReference)
  /// `<scheme>://items?…`: the ordered list, possibly empty when every key
  /// was unknown or malformed.
  case list([ItemLinkReference])
}

/// Parses the app-scheme item links. Pure so the URL contract is tested
/// without AppKit, the network, or the auth callback.
///
/// The scheme is not checked here: macOS only delivers URLs for the schemes
/// this bundle registered (`omi-computer`, `omi-computer-dev`, or a named
/// bundle's `omi-<slug>`), and the auth callback shares the same scheme.
enum ItemLinkParser {
  /// The contract's cap; keys past it are ignored.
  static let maxItems = 10
  /// Ids are interpolated into authenticated API paths
  /// (`v1/conversations/<id>`), so only plain identifier characters are
  /// accepted. A decoded `/`, `?`, `#`, `%` or `..` could otherwise steer the
  /// request to a different endpoint.
  static let maxIDLength = 128

  static func parse(_ url: URL) -> ItemLinkRoute? {
    guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
      let host = components.host?.lowercased(), !host.isEmpty
    else { return nil }

    if host == "items" {
      // Tolerate a trailing slash (`items/?…`) but nothing deeper.
      guard components.path.isEmpty || components.path == "/" else { return nil }
      return .list(references(from: components.queryItems ?? []))
    }

    guard let kind = ItemLinkKind(rawValue: host) else { return nil }
    let segments = components.path.split(separator: "/", omittingEmptySubsequences: true)
    guard segments.count == 1 else { return nil }
    // `URLComponents.path` is percent-decoded; validation runs on the decoded
    // value so an encoded separator cannot pass as part of an id.
    let id = String(segments[0])
    guard isValidID(id) else { return nil }
    return .single(ItemLinkReference(kind: kind, id: id))
  }

  /// Ordered, de-duplicated, capped references from the query. Unknown keys
  /// and malformed ids are skipped without consuming a slot.
  static func references(from queryItems: [URLQueryItem]) -> [ItemLinkReference] {
    var seen = Set<ItemLinkReference>()
    var result: [ItemLinkReference] = []
    for item in queryItems {
      guard result.count < maxItems else { break }
      guard let kind = ItemLinkKind(rawValue: item.name),
        let id = item.value, isValidID(id)
      else { continue }
      let reference = ItemLinkReference(kind: kind, id: id)
      guard seen.insert(reference).inserted else { continue }
      result.append(reference)
    }
    return result
  }

  static func isValidID(_ id: String) -> Bool {
    guard !id.isEmpty, id.count <= maxIDLength else { return false }
    return id.unicodeScalars.allSatisfy { scalar in
      switch scalar {
      case "a"..."z", "A"..."Z", "0"..."9", "-", "_": return true
      default: return false
      }
    }
  }
}
