import Foundation

/// Bounded memo for immutable render results. Hits relink one node instead of
/// comparing every cached Markdown string during each streaming frame.
@MainActor
final class ChatRenderLRU<Key: Hashable, Value> {
  private final class Node {
    let key: Key
    let value: Value
    weak var previous: Node?
    var next: Node?

    init(key: Key, value: Value) {
      self.key = key
      self.value = value
    }
  }

  private let capacity: Int
  private var nodes: [Key: Node] = [:]
  private var oldest: Node?
  private var newest: Node?

  init(capacity: Int) {
    precondition(capacity > 0)
    self.capacity = capacity
  }

  var count: Int { nodes.count }

  func value(for key: Key, produce: () -> Value?) -> Value? {
    if let node = nodes[key] {
      if node !== newest {
        unlink(node)
        append(node)
      }
      return node.value
    }
    guard let value = produce() else { return nil }
    let node = Node(key: key, value: value)
    nodes[key] = node
    append(node)
    if nodes.count > capacity, let victim = oldest {
      unlink(victim)
      nodes[victim.key] = nil
    }
    return value
  }

  func removeAll() {
    // Detach iteratively so a full cache does not recursively destroy its chain.
    while let node = oldest { unlink(node) }
    nodes.removeAll()
  }

  private func unlink(_ node: Node) {
    if let previous = node.previous { previous.next = node.next } else { oldest = node.next }
    if let next = node.next { next.previous = node.previous } else { newest = node.previous }
    node.previous = nil
    node.next = nil
  }

  private func append(_ node: Node) {
    node.previous = newest
    newest?.next = node
    if oldest == nil { oldest = node }
    newest = node
  }
}

/// Rebuilding parent chrome must not reparse every unchanged answer. Keep the
/// parser pure, and memoize at the UI boundary where its output is consumed.
@MainActor
enum ChatMarkdownRenderCache {
  private static let documents = ChatRenderLRU<String, OmiMarkdownDocument>(capacity: 1_024)

  static func document(for text: String) -> OmiMarkdownDocument {
    if let cached = documents.value(for: text, produce: { nil }) { return cached }
    let document = OmiMarkdownDocument(markdown: text)
    _ = documents.value(for: text) { document }
    return document
  }
}
