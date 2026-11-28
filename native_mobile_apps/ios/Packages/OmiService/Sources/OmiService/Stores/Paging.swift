import Foundation

/// Offset paging for lists the stores load whole (tasks, memories).
@MainActor
enum Paging {
    /// Fetches pages until one comes back short. `maxPages` guards against a backend that ignores `offset`.
    static func all<Item>(
        pageSize: Int,
        maxPages: Int = 100,
        fetch: (_ limit: Int, _ offset: Int) async throws -> [Item]
    ) async throws -> [Item] {
        var items: [Item] = []
        for _ in 0 ..< maxPages {
            let page = try await fetch(pageSize, items.count)
            items += page
            if page.count < pageSize { break }
        }
        return items
    }
}
