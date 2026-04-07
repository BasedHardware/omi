import AppKit
import Foundation

enum MemoryExportDestination: String, CaseIterable, Identifiable, Sendable {
  case notion
  case obsidian
  case chatgpt
  case claude
  case gemini

  var id: String { rawValue }

  var title: String {
    switch self {
    case .notion: return "Notion"
    case .obsidian: return "Obsidian"
    case .chatgpt: return "ChatGPT"
    case .claude: return "Claude"
    case .gemini: return "Gemini"
    }
  }

  var subtitle: String {
    switch self {
    case .notion: return "Copy-ready page export"
    case .obsidian: return "Choose once, refresh anytime"
    case .chatgpt: return "Prompt + memory pack"
    case .claude: return "Prompt + memory pack"
    case .gemini: return "Prompt + memory pack"
    }
  }

  var description: String {
    switch self {
    case .notion: return "Copy a ready-to-paste memory page and jump into Notion."
    case .obsidian: return "Write Omi memories into your Obsidian vault."
    case .chatgpt: return "Copy the prompt and memory pack, then open ChatGPT."
    case .claude: return "Copy the prompt and memory pack, then open Claude."
    case .gemini: return "Copy the prompt and memory pack, then open Gemini."
    }
  }

  var brand: ConnectorBrand {
    switch self {
    case .notion: return .notion
    case .obsidian: return .obsidian
    case .chatgpt: return .chatgpt
    case .claude: return .claude
    case .gemini: return .gemini
    }
  }

  var isAutomated: Bool {
    switch self {
    case .obsidian:
      return true
    case .notion, .chatgpt, .claude, .gemini:
      return false
    }
  }

  var browserURL: URL? {
    switch self {
    case .notion:
      return URL(string: "https://www.notion.so/")
    case .obsidian:
      return nil
    case .chatgpt:
      return URL(string: "https://chatgpt.com/")
    case .claude:
      return URL(string: "https://claude.ai/new")
    case .gemini:
      return URL(string: "https://gemini.google.com/app")
    }
  }

  var manualPrompt: String {
    switch self {
    case .notion:
      return ""
    case .chatgpt:
      return """
        I’m attaching an Omi memory export. Read it carefully and keep the durable facts, preferences, projects, relationships, and goals as working context for future conversations with me. Start by giving me a concise profile summary of what you learned.
        """
    case .claude:
      return """
        I’m attaching an Omi memory export. Absorb the durable facts about me, including projects, habits, preferences, relationships, and goals, and use them as context for future conversations. Start by summarizing the most important things you learned about me.
        """
    case .gemini:
      return """
        I’m attaching an Omi memory export. Read it as persistent context about me and keep the durable facts, preferences, projects, and goals in mind for future chats. Start with a short profile summary of what stands out.
        """
    case .obsidian:
      return ""
    }
  }

  func clipboardText(for markdown: String) -> String {
    switch self {
    case .notion:
      return markdown
    case .chatgpt, .claude, .gemini:
      return """
        \(manualPrompt)

        ---

        \(markdown)
        """
    case .obsidian:
      return markdown
    }
  }

  fileprivate var notionTokenKey: String { "memoryExportNotionToken" }
  fileprivate var notionParentPageKey: String { "memoryExportNotionParentPageID" }
  fileprivate var obsidianVaultPathKey: String { "memoryExportObsidianVaultPath" }
  fileprivate var exportedCountKey: String { "memoryExportExportedCount.\(rawValue)" }
  fileprivate var lastExportedAtKey: String { "memoryExportLastExportedAt.\(rawValue)" }
  fileprivate var detailKey: String { "memoryExportDetail.\(rawValue)" }
  fileprivate var lastExportPathKey: String { "memoryExportLastExportPath.\(rawValue)" }
}

struct MemoryExportStatus: Sendable {
  let exportedCount: Int
  let lastExportedAt: Date?
  let detailText: String?
  let isConfigured: Bool
}

struct MemoryExportResult: Sendable {
  let memoryCount: Int
  let detailText: String?
  let destinationURL: URL?
  let fileURL: URL?
  let clipboardText: String?
}

enum MemoryExportError: LocalizedError {
  case noMemories
  case invalidNotionConfiguration
  case invalidNotionResponse
  case invalidObsidianVault
  case requestFailed(String)

  var errorDescription: String? {
    switch self {
    case .noMemories:
      return "There are no memories available to export yet."
    case .invalidNotionConfiguration:
      return "Enter both a Notion integration token and a parent page ID."
    case .invalidNotionResponse:
      return "Notion returned an unexpected response."
    case .invalidObsidianVault:
      return "Choose a valid Obsidian vault folder first."
    case .requestFailed(let message):
      return message
    }
  }
}

actor MemoryExportService {
  static let shared = MemoryExportService()

  private let defaults = UserDefaults.standard
  private let notionVersion = "2026-03-11"
  private let notionBaseURL = URL(string: "https://api.notion.com/v1")!

  func status(for destination: MemoryExportDestination) -> MemoryExportStatus {
    let exportedCount = max(defaults.integer(forKey: destination.exportedCountKey), 0)

    let lastExportedAt: Date?
    if defaults.object(forKey: destination.lastExportedAtKey) != nil {
      let timestamp = defaults.double(forKey: destination.lastExportedAtKey)
      lastExportedAt = timestamp > 0 ? Date(timeIntervalSince1970: timestamp) : nil
    } else {
      lastExportedAt = nil
    }

    let detailText = defaults.string(forKey: destination.detailKey)
    let isConfigured: Bool
    switch destination {
    case .obsidian:
      isConfigured = !(defaults.string(forKey: destination.obsidianVaultPathKey) ?? "").isEmpty
    case .notion, .chatgpt, .claude, .gemini:
      isConfigured = exportedCount > 0
    }

    return MemoryExportStatus(
      exportedCount: exportedCount,
      lastExportedAt: lastExportedAt,
      detailText: detailText,
      isConfigured: isConfigured
    )
  }

  func allStatuses() -> [MemoryExportDestination: MemoryExportStatus] {
    Dictionary(
      uniqueKeysWithValues: MemoryExportDestination.allCases.map { destination in
        (destination, status(for: destination))
      })
  }

  func notionConfiguration() -> (token: String, parentPageID: String) {
    (
      defaults.string(forKey: MemoryExportDestination.notion.notionTokenKey) ?? "",
      defaults.string(forKey: MemoryExportDestination.notion.notionParentPageKey) ?? ""
    )
  }

  func obsidianVaultPath() -> String {
    defaults.string(forKey: MemoryExportDestination.obsidian.obsidianVaultPathKey) ?? ""
  }

  func exportToNotion(token: String, parentPageID: String) async throws -> MemoryExportResult {
    let sanitizedToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
    let sanitizedParentPageID = parentPageID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !sanitizedToken.isEmpty, !sanitizedParentPageID.isEmpty else {
      throw MemoryExportError.invalidNotionConfiguration
    }

    let memories = try await fetchMemories(limit: 250)
    guard !memories.isEmpty else { throw MemoryExportError.noMemories }

    let pageTitle = "Omi Memory Export \(Self.exportTitleFormatter.string(from: Date()))"
    let pageID = try await createNotionPage(
      token: sanitizedToken,
      parentPageID: sanitizedParentPageID,
      title: pageTitle
    )
    try await appendNotionBlocks(
      token: sanitizedToken,
      pageID: pageID,
      memories: memories
    )

    defaults.set(sanitizedToken, forKey: MemoryExportDestination.notion.notionTokenKey)
    defaults.set(sanitizedParentPageID, forKey: MemoryExportDestination.notion.notionParentPageKey)

    let detail = "Exported to Notion"
    persistStatus(
      destination: .notion,
      exportedCount: memories.count,
      detailText: detail,
      filePath: nil
    )

    return MemoryExportResult(
      memoryCount: memories.count,
      detailText: detail,
      destinationURL: URL(string: "https://www.notion.so/"),
      fileURL: nil,
      clipboardText: nil
    )
  }

  func exportToObsidian(vaultURL: URL) async throws -> MemoryExportResult {
    let path = vaultURL.path.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !path.isEmpty else { throw MemoryExportError.invalidObsidianVault }

    let memories = try await fetchMemories(limit: 400)
    guard !memories.isEmpty else { throw MemoryExportError.noMemories }

    let exportDirectory = vaultURL.appendingPathComponent("Omi", isDirectory: true)
    try FileManager.default.createDirectory(
      at: exportDirectory,
      withIntermediateDirectories: true,
      attributes: nil
    )

    let exportFileURL = exportDirectory.appendingPathComponent("Memories.md")
    let markdown = buildMarkdownPack(memories: memories, destination: .obsidian)
    try markdown.write(to: exportFileURL, atomically: true, encoding: .utf8)

    defaults.set(path, forKey: MemoryExportDestination.obsidian.obsidianVaultPathKey)

    let detail = "Updated Obsidian vault"
    persistStatus(
      destination: .obsidian,
      exportedCount: memories.count,
      detailText: detail,
      filePath: exportFileURL.path
    )

    let openURL = obsidianOpenURL(vaultURL: vaultURL, notePath: "Omi/Memories")
    return MemoryExportResult(
      memoryCount: memories.count,
      detailText: detail,
      destinationURL: openURL,
      fileURL: exportFileURL,
      clipboardText: nil
    )
  }

  func prepareManualExport(for destination: MemoryExportDestination) async throws
    -> MemoryExportResult
  {
    precondition(!destination.isAutomated, "prepareManualExport only supports manual destinations")

    let memories = try await fetchMemories(limit: 400)
    guard !memories.isEmpty else { throw MemoryExportError.noMemories }

    let directory = try exportDirectory()
    let fileURL = directory.appendingPathComponent(
      "\(destination.rawValue)-memory-pack-\(Self.fileStampFormatter.string(from: Date())).md"
    )

    let markdown = buildMarkdownPack(memories: memories, destination: destination)
    try markdown.write(to: fileURL, atomically: true, encoding: .utf8)

    let detail = "Memory pack ready"
    persistStatus(
      destination: destination,
      exportedCount: memories.count,
      detailText: detail,
      filePath: fileURL.path
    )

    return MemoryExportResult(
      memoryCount: memories.count,
      detailText: detail,
      destinationURL: destination.browserURL,
      fileURL: fileURL,
      clipboardText: destination.clipboardText(for: markdown)
    )
  }

  private func fetchMemories(limit: Int) async throws -> [ServerMemory] {
    do {
      let remoteMemories = try await APIClient.shared.getMemories(limit: limit)
      if !remoteMemories.isEmpty {
        return remoteMemories
      }
    } catch {
      log("MemoryExportService: Remote memory fetch failed, falling back to local cache: \(error)")
    }

    let localMemories = try await MemoryStorage.shared.getLocalMemories(limit: limit)
    if !localMemories.isEmpty {
      return localMemories
    }

    throw MemoryExportError.noMemories
  }

  private func buildMarkdownPack(
    memories: [ServerMemory],
    destination: MemoryExportDestination
  ) -> String {
    var lines: [String] = [
      "# Omi Memory Export",
      "",
      "Generated: \(Self.exportTitleFormatter.string(from: Date()))",
      "Destination: \(destination.title)",
      "Total memories: \(memories.count)",
      "",
      "## Durable memories",
    ]

    for memory in memories {
      let sourceApp = memory.sourceApp?.trimmingCharacters(in: .whitespacesAndNewlines)
      let sourcePrefix = (sourceApp?.isEmpty == false) ? "[\(sourceApp!)] " : ""
      let content = memory.content
        .replacingOccurrences(of: "\n", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !content.isEmpty else { continue }
      lines.append("- \(sourcePrefix)\(content)")
    }

    lines.append("")
    lines.append("## How to use this")
    if destination.isAutomated {
      lines.append("This export was generated by Omi and can be refreshed at any time.")
    } else {
      lines.append(
        "Upload or paste this export into \(destination.title) together with the copied prompt.")
    }

    return lines.joined(separator: "\n")
  }

  private func exportDirectory() throws -> URL {
    let downloads =
      FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
      ?? FileManager.default.homeDirectoryForCurrentUser
    let directory = downloads.appendingPathComponent("Omi Exports", isDirectory: true)
    try FileManager.default.createDirectory(
      at: directory,
      withIntermediateDirectories: true,
      attributes: nil
    )
    return directory
  }

  private func persistStatus(
    destination: MemoryExportDestination,
    exportedCount: Int,
    detailText: String?,
    filePath: String?
  ) {
    defaults.set(exportedCount, forKey: destination.exportedCountKey)
    defaults.set(Date().timeIntervalSince1970, forKey: destination.lastExportedAtKey)
    defaults.set(detailText, forKey: destination.detailKey)
    if let filePath {
      defaults.set(filePath, forKey: destination.lastExportPathKey)
    }
  }

  private func createNotionPage(token: String, parentPageID: String, title: String) async throws
    -> String
  {
    let url = notionBaseURL.appendingPathComponent("pages")
    var request = notionRequest(url: url, token: token)
    request.httpMethod = "POST"

    let body: [String: Any] = [
      "parent": ["page_id": parentPageID],
      "properties": [
        "title": [
          "title": [
            [
              "type": "text",
              "text": ["content": title],
            ]
          ]
        ]
      ],
    ]

    request.httpBody = try JSONSerialization.data(withJSONObject: body)
    let (data, response) = try await URLSession.shared.data(for: request)
    try validateNotionResponse(data: data, response: response)

    guard
      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let pageID = json["id"] as? String
    else {
      throw MemoryExportError.invalidNotionResponse
    }

    return pageID
  }

  private func appendNotionBlocks(token: String, pageID: String, memories: [ServerMemory])
    async throws
  {
    let url = notionBaseURL.appendingPathComponent("blocks/\(pageID)/children")
    let chunks = notionChildren(memories: memories).chunked(into: 100)

    for chunk in chunks where !chunk.isEmpty {
      var request = notionRequest(url: url, token: token)
      request.httpMethod = "PATCH"
      request.httpBody = try JSONSerialization.data(withJSONObject: ["children": chunk])
      let (data, response) = try await URLSession.shared.data(for: request)
      try validateNotionResponse(data: data, response: response)
    }
  }

  private func notionRequest(url: URL, token: String) -> URLRequest {
    var request = URLRequest(url: url)
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue(notionVersion, forHTTPHeaderField: "Notion-Version")
    request.timeoutInterval = 30
    return request
  }

  private func validateNotionResponse(data: Data, response: URLResponse) throws {
    guard let httpResponse = response as? HTTPURLResponse else {
      throw MemoryExportError.requestFailed("Notion did not return a valid HTTP response.")
    }

    guard (200..<300).contains(httpResponse.statusCode) else {
      let message: String
      if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let detail = json["message"] as? String
      {
        message = detail
      } else {
        message = HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode)
      }
      throw MemoryExportError.requestFailed("Notion export failed: \(message)")
    }
  }

  private func notionChildren(memories: [ServerMemory]) -> [[String: Any]] {
    var children: [[String: Any]] = [
      headingBlock(level: 1, text: "Omi Memory Export"),
      paragraphBlock(text: "Generated \(Self.exportTitleFormatter.string(from: Date()))"),
      headingBlock(level: 2, text: "Durable memories"),
    ]

    children.append(
      contentsOf: memories.compactMap { memory in
        let content = memory.content
          .replacingOccurrences(of: "\n", with: " ")
          .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return nil }
        return bulletBlock(text: String(content.prefix(1800)))
      }
    )

    return children
  }

  private func headingBlock(level: Int, text: String) -> [String: Any] {
    let type = "heading_\(level)"
    return [
      "object": "block",
      "type": type,
      type: ["rich_text": richText(text: text)],
    ]
  }

  private func paragraphBlock(text: String) -> [String: Any] {
    [
      "object": "block",
      "type": "paragraph",
      "paragraph": ["rich_text": richText(text: text)],
    ]
  }

  private func bulletBlock(text: String) -> [String: Any] {
    [
      "object": "block",
      "type": "bulleted_list_item",
      "bulleted_list_item": ["rich_text": richText(text: text)],
    ]
  }

  private func richText(text: String) -> [[String: Any]] {
    [
      [
        "type": "text",
        "text": ["content": text],
      ]
    ]
  }

  private func obsidianOpenURL(vaultURL: URL, notePath: String) -> URL? {
    var components = URLComponents()
    components.scheme = "obsidian"
    components.host = "open"
    components.queryItems = [
      URLQueryItem(name: "vault", value: vaultURL.lastPathComponent),
      URLQueryItem(name: "file", value: notePath),
    ]
    return components.url
  }

  private static let exportTitleFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short
    return formatter
  }()

  private static let fileStampFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyyMMdd-HHmm"
    return formatter
  }()
}

extension Array {
  fileprivate func chunked(into size: Int) -> [[Element]] {
    guard size > 0 else { return [self] }
    return stride(from: 0, to: count, by: size).map { start in
      Array(self[start..<Swift.min(start + size, count)])
    }
  }
}
