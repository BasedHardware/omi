import Foundation

/// Anchor for `Bundle(for:)`. `swift test` does not point `Bundle.main` at the
/// xctest that holds the resource bundle, and a pure Swift class cannot be
/// passed to `Bundle(for:)`.
private final class ProductKnowledgeBundleToken: NSObject {}

/// One shipped product-knowledge article. `sources` names the code the facts
/// were checked against; the tool result omits those paths.
struct ProductKnowledgeDocument: Equatable, Sendable {
  let id: String
  let title: String
  let keywords: [String]
  let sources: [String]
  let body: String
}

/// The product guide bundled with this build of the app.
struct ProductKnowledgeLibrary: Equatable, Sendable {
  let documents: [ProductKnowledgeDocument]

  /// Reads the resource bundle shipped with the app. Missing files yield nil
  /// rather than a substitute article.
  static func loadBundled() -> ProductKnowledgeLibrary? {
    load(from: bundledRoots())
  }

  static func load(from roots: [URL]) -> ProductKnowledgeLibrary? {
    guard let indexURL = findIndex(in: roots),
      let data = try? Data(contentsOf: indexURL),
      let index = try? JSONDecoder().decode(IndexFile.self, from: data),
      !index.docs.isEmpty
    else { return nil }

    var documents: [ProductKnowledgeDocument] = []
    var seen = Set<String>()
    for entry in index.docs {
      let id = entry.id.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !id.isEmpty, seen.insert(id).inserted else { return nil }
      guard let fileURL = resolve(file: entry.file, indexURL: indexURL, roots: roots),
        let text = try? String(contentsOf: fileURL, encoding: .utf8),
        let document = parse(markdown: text, indexID: id, indexTitle: entry.title)
      else { return nil }
      documents.append(document)
    }
    return ProductKnowledgeLibrary(documents: documents)
  }

  func answer(query rawQuery: String?, topic rawTopic: String?) -> String {
    let topic = rawTopic?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let query = rawQuery?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if topic.isEmpty && query.isEmpty {
      return listText()
    }
    if !topic.isEmpty {
      let key = Self.normalize(topic)
      if let document = documents.first(where: {
        Self.normalize($0.id) == key || Self.normalize($0.title) == key
      }) {
        return render([document])
      }
      if query.isEmpty {
        return Self.noMatchText(documents: documents)
      }
    }
    let matches = ranked(query: query)
    guard !matches.isEmpty else { return Self.noMatchText(documents: documents) }
    return render(matches)
  }

  private func listText() -> String {
    let lines = documents.map { "- \($0.id): \($0.title)" }
    return (["Product knowledge topics:"] + lines).joined(separator: "\n")
  }

  private func ranked(query: String) -> [ProductKnowledgeDocument] {
    let scored = documents.enumerated().compactMap { index, document -> Scored? in
      let points = self.score(document, query: query)
      guard points > 0 else { return nil }
      return Scored(score: points, index: index, document: document)
    }
    guard let best = scored.map(\.score).max() else { return [] }
    let cutoff = max(1, best * 6 / 10)
    return scored.filter { $0.score >= cutoff }
      .sorted { lhs, rhs in
        if lhs.score != rhs.score { return lhs.score > rhs.score }
        return lhs.index < rhs.index
      }
      .prefix(2)
      .map(\.document)
  }

  private func score(_ document: ProductKnowledgeDocument, query: String) -> Int {
    let normalizedQuery = Self.normalize(query)
    guard !normalizedQuery.isEmpty else { return 0 }
    var score = 0
    let phrases = document.keywords + [document.title, document.id.replacingOccurrences(of: "-", with: " ")]
    for phrase in phrases {
      let normalized = Self.normalize(phrase)
      guard normalized.count >= 4 else { continue }
      if normalizedQuery.contains(normalized) || normalized.contains(normalizedQuery) {
        score += 10 + min(normalized.count, 40)
      }
    }
    let queryTokens = Set(Self.tokens(normalizedQuery))
    let documentTokens = Set(phrases.flatMap { Self.tokens(Self.normalize($0)) })
    score += queryTokens.intersection(documentTokens).count * 3
    return score
  }

  private func render(_ documents: [ProductKnowledgeDocument]) -> String {
    let sections = documents.map { "# \($0.title) (\($0.id))\n\n\($0.body)" }
    var text = sections.joined(separator: "\n\n")
    let limit = ProductKnowledgeTool.maxResultCharacters
    if text.count > limit {
      let end = text.index(text.startIndex, offsetBy: limit)
      text = String(text[..<end]) + "\n[truncated]"
    }
    return text
  }

  private static func noMatchText(documents: [ProductKnowledgeDocument]) -> String {
    let topics = documents.map { "\($0.id) (\($0.title))" }.joined(separator: "; ")
    return "\(ProductKnowledgeTool.noMatchMessage)\nTopics: \(topics)."
  }

  /// App installs nest the SwiftPM resource bundle under `Contents/Resources`.
  /// `swift test` nests that same bundle inside the xctest bundle, and
  /// `Bundle.main` during a test is not that xctest. Search both, plus any
  /// already-loaded bundle, and never trap when the guide is absent.
  static func bundledRoots() -> [URL] {
    var anchors = [Bundle.main.bundleURL, Bundle(for: ProductKnowledgeBundleToken.self).bundleURL]
    for bundle in Bundle.allBundles {
      anchors.append(bundle.bundleURL)
      if let resourceURL = bundle.resourceURL { anchors.append(resourceURL) }
    }

    var roots: [URL] = []
    var seen = Set<String>()
    func add(_ url: URL) {
      let path = url.standardizedFileURL.path
      guard seen.insert(path).inserted else { return }
      roots.append(url)
    }

    for anchor in anchors {
      var cursor = anchor
      for _ in 0..<6 {
        for root in OmiBrandMarkAsset.knownResourceBundleRoots(in: cursor) {
          add(root)
        }
        let children =
          (try? FileManager.default.contentsOfDirectory(at: cursor, includingPropertiesForKeys: nil)) ?? []
        for child in children where child.pathExtension == "bundle" {
          add(child)
          add(child.appendingPathComponent("Contents/Resources"))
        }
        let parent = cursor.deletingLastPathComponent()
        if parent.path == cursor.path { break }
        cursor = parent
      }
    }
    return roots
  }

  private static func findIndex(in roots: [URL]) -> URL? {
    for root in roots {
      for relative in ["ProductKnowledge/product-knowledge-index.json", "product-knowledge-index.json"] {
        let candidate = root.appendingPathComponent(relative)
        if FileManager.default.isReadableFile(atPath: candidate.path) { return candidate }
      }
    }
    return nil
  }

  private static func resolve(file: String, indexURL: URL, roots: [URL]) -> URL? {
    var candidates = [indexURL.deletingLastPathComponent().appendingPathComponent(file)]
    for root in roots {
      candidates.append(root.appendingPathComponent(file))
      candidates.append(root.appendingPathComponent("ProductKnowledge").appendingPathComponent(file))
    }
    return candidates.first { FileManager.default.isReadableFile(atPath: $0.path) }
  }

  private static func parse(markdown: String, indexID: String, indexTitle: String) -> ProductKnowledgeDocument? {
    let trimmed = markdown.replacingOccurrences(of: "\r\n", with: "\n")
    var title = indexTitle.trimmingCharacters(in: .whitespacesAndNewlines)
    var keywords: [String] = []
    var sources: [String] = []
    var body = trimmed
    if trimmed.hasPrefix("---\n") {
      let rest = trimmed.dropFirst(4)
      guard let closing = rest.range(of: "\n---\n") else { return nil }
      let header = String(rest[..<closing.lowerBound])
      body = String(rest[closing.upperBound...])
      var listKey: String?
      for rawLine in header.split(separator: "\n", omittingEmptySubsequences: false) {
        let line = String(rawLine)
        if line.hasPrefix("- ") || line.hasPrefix("  - ") {
          let item = line.trimmingCharacters(in: .whitespaces).dropFirst(2)
            .trimmingCharacters(in: .whitespaces)
          if listKey == "sources", !item.isEmpty { sources.append(String(item)) }
          continue
        }
        listKey = nil
        guard let colon = line.firstIndex(of: ":") else { continue }
        let key = String(line[..<colon]).trimmingCharacters(in: .whitespaces)
        let value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
        if value.isEmpty {
          listKey = key
          continue
        }
        switch key {
        case "id":
          guard normalize(value) == normalize(indexID) else { return nil }
        case "title":
          title = value
        case "keywords":
          keywords = value.split(separator: ",").map {
            $0.trimmingCharacters(in: .whitespaces)
          }.filter { !$0.isEmpty }
        default:
          break
        }
      }
    }
    let cleaned = body.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !title.isEmpty, !cleaned.isEmpty, !sources.isEmpty else { return nil }
    return ProductKnowledgeDocument(
      id: indexID, title: title, keywords: keywords, sources: sources, body: cleaned)
  }

  private static func normalize(_ value: String) -> String {
    let lowered = value.lowercased()
    let mapped = lowered.map { character -> Character in
      character.isLetter || character.isNumber ? character : " "
    }
    return String(mapped).split(separator: " ").joined(separator: " ")
  }

  private static func tokens(_ normalized: String) -> [String] {
    normalized.split(separator: " ").map(String.init).filter { token in
      token.count >= 4 && !stopwords.contains(token)
    }
  }

  private static let stopwords: Set<String> = [
    "about", "after", "does", "enable", "from", "have", "that", "this", "what", "when", "where",
    "with", "your",
  ]

  private struct IndexFile: Decodable {
    var docs: [IndexEntry]
  }

  private struct IndexEntry: Decodable {
    var id: String
    var file: String
    var title: String
  }

  private struct Scored {
    var score: Int
    var index: Int
    var document: ProductKnowledgeDocument
  }
}

/// Local read of the shipped product guide. No network, and no invented text
/// when the bundle is missing.
enum ProductKnowledgeTool {
  static let unavailableMessage = "knowledge base unavailable"
  static let noMatchMessage = "No product knowledge matched that query."
  static let maxResultCharacters = 6_000

  static func execute(arguments: [String: Any]) -> String {
    execute(
      query: arguments["query"] as? String,
      topic: arguments["topic"] as? String,
      library: ProductKnowledgeLibrary.loadBundled())
  }

  static func execute(query: String?, topic: String?, library: ProductKnowledgeLibrary?) -> String {
    guard let library, !library.documents.isEmpty else { return unavailableMessage }
    return library.answer(query: query, topic: topic)
  }
}
