import Foundation

/// Memoizes the atlas layout across view reconstructions.
///
/// `CanonicalMemoryAtlasSurface` builds its snapshot in `init`, which SwiftUI
/// re-runs whenever the parent re-renders. That was affordable when placement
/// was a closed-form function of type and rank; relaxing a thousand-entity
/// graph is not, and recomputing it would also make the map visibly reshuffle
/// for no reason the user caused.
///
/// The key is the graph's content, so a snapshot is reused exactly when it
/// would have been recomputed identically, and dropped the moment the graph
/// actually changes.
final class MemoryAtlasSnapshotCache: @unchecked Sendable {
  /// Deliberately tiny. In practice one entry serves the whole session; the
  /// spares cover a rebuild landing while the previous graph is still on
  /// screen, and the compact/full surfaces briefly disagreeing.
  private static let capacity = 3

  static let shared = MemoryAtlasSnapshotCache()

  struct Key: Hashable {
    let userName: String?
    let nodeCount: Int
    let edgeCount: Int
    let digest: Int
  }

  /// Guards every stored property below. The class is `@unchecked Sendable`
  /// because this lock — not the compiler — is what makes it safe.
  private let lock = NSLock()
  private var entries: [(key: Key, snapshot: MemoryAtlasSnapshot)] = []
  private var computes = 0
  private var reuses = 0

  /// Counted rather than timed, so the performance harness asserts the same
  /// thing on every Mac.
  var computeCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return computes
  }

  var reuseCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return reuses
  }

  func snapshot(for graph: KnowledgeGraphResponse, userName: String?) -> MemoryAtlasSnapshot {
    let key = Self.makeKey(for: graph, userName: userName)

    lock.lock()
    if let index = entries.firstIndex(where: { $0.key == key }) {
      let hit = entries.remove(at: index)
      entries.append(hit)
      reuses += 1
      lock.unlock()
      return hit.snapshot
    }
    computes += 1
    lock.unlock()

    // Deliberately computed outside the lock: this is the expensive call, and
    // holding a lock across it would serialize unrelated surfaces. A duplicate
    // computation under a race is wasteful but not wrong — the function is pure.
    let snapshot = MemoryAtlasLayoutEngine.makeSnapshot(graph: graph, userName: userName)

    lock.lock()
    entries.removeAll { $0.key == key }
    entries.append((key, snapshot))
    if entries.count > Self.capacity { entries.removeFirst(entries.count - Self.capacity) }
    lock.unlock()

    return snapshot
  }

  /// Content digest over everything the snapshot reads.
  ///
  /// The memory ids are hashed individually rather than counted. Co-occurrence
  /// is derived from *which* memories two entities share, so a node swapping
  /// one memory for another changes the whole layout while leaving every count
  /// identical — a digest over counts would serve the previous map back and
  /// look like the rebuild had silently done nothing.
  ///
  /// Hashing a few thousand short strings costs well under a millisecond,
  /// against tens of milliseconds for the relaxation it protects.
  static func makeKey(for graph: KnowledgeGraphResponse, userName: String?) -> Key {
    var hasher = Hasher()
    for node in graph.nodes {
      hasher.combine(node.id)
      hasher.combine(node.label)
      hasher.combine(node.nodeType)
      hasher.combine(node.aliases)
      hasher.combine(node.memoryIds)
      // The replay timeline is built from these, so they are part of the
      // snapshot even though they never move a node.
      hasher.combine(node.createdAt)
      hasher.combine(node.updatedAt)
    }
    for node in graph.catalogNodes ?? [] {
      hasher.combine(node.id)
      hasher.combine(node.label)
      hasher.combine(node.nodeType)
      hasher.combine(node.aliases)
      hasher.combine(node.memoryIds)
      hasher.combine(node.createdAt)
      hasher.combine(node.updatedAt)
    }
    for edge in graph.edges {
      hasher.combine(edge.id)
      hasher.combine(edge.sourceId)
      hasher.combine(edge.targetId)
      hasher.combine(edge.label)
      hasher.combine(edge.memoryIds)
      hasher.combine(edge.createdAt)
    }
    return Key(
      userName: userName,
      nodeCount: graph.nodes.count,
      edgeCount: graph.edges.count,
      digest: hasher.finalize())
  }

  /// Tests share a process, so a stale entry from one case would otherwise
  /// satisfy the next.
  func resetForTesting() {
    lock.lock()
    entries.removeAll()
    computes = 0
    reuses = 0
    lock.unlock()
  }
}
