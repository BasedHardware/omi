//
//  ServerPaging.swift — the two things offset paging against this backend gets wrong.
//
//  Both desktop lists page the same backend the same way, and both had the same two bugs in them.
//
//  **1. A short page is not the last page.** `GET /v3/memories` fetches `limit` documents from
//  Firestore and then drops the rejected, superseded and unparseable ones *in Python* before
//  answering (`backend/database/memories.py`), so a request for 100 routinely returns 97.
//  `GET /v1/conversations` post-filters the same way. Reading that as the end was silent and total:
//  one 97-row answer set `hasMoreMemories = false` and the account's other five thousand memories
//  became unreachable for the rest of the session — no error, no footer, just a list that stopped.
//  Only an empty page proves the end. That costs exactly one extra request per list, at the end.
//
//  **2. An offset is not a stable cursor.** The memories query orders by `scoring desc, created_at
//  desc` and `scoring` is mutable, so a row can move between two pages fetched seconds apart and
//  arrive in both — or in neither. That was survivable while one page was ever fetched; it is a
//  certainty once the whole account is paged in. So a page is merged by identity rather than
//  appended, and the first sighting of a row wins.
//

import Foundation

enum ServerPaging {
  /// Whether another page is worth asking for.
  ///
  /// - Parameters:
  ///   - received: rows this page actually returned. Zero is the end, unconditionally.
  ///   - loaded: rows held after this page.
  ///   - total: the server's own count for the same query, when the caller has an authoritative
  ///     one. `nil` means "unknown", which is not the same as zero and must not stop paging. The
  ///     empty page still wins, so a count that disagrees with the list cannot page forever.
  static func hasMore(received: Int, loaded: Int = 0, total: Int? = nil) -> Bool {
    guard received > 0 else { return false }
    guard let total else { return true }
    return loaded < total
  }

  /// Adds a page to a list, keeping the rows already held and their order.
  ///
  /// Deliberately not a `Set` round trip: order *is* the list here, and re-sorting a paged list on
  /// every append is both wrong and expensive.
  static func appending<Element, Key: Hashable>(
    _ page: [Element], to existing: [Element], by key: KeyPath<Element, Key>
  ) -> [Element] {
    guard !page.isEmpty else { return existing }
    var seen = Set(existing.map { $0[keyPath: key] })
    seen.reserveCapacity(existing.count + page.count)
    var merged = existing
    merged.reserveCapacity(existing.count + page.count)
    for element in page where seen.insert(element[keyPath: key]).inserted {
      merged.append(element)
    }
    return merged
  }
}
