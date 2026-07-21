import Foundation

extension MemoryExportService {
  /// Writes memories to the "Omi Memories" page in the connected Notion
  /// workspace over Notion's hosted MCP (create once, replace on later syncs).
  func exportToNotion() async throws -> MemoryExportResult {
    let memories = try await fetchMemories(limit: 400)
    guard !memories.isEmpty else { throw MemoryExportError.noMemories }

    let markdown = buildMarkdownPack(memories: memories, destination: .notion)
    let pageURL = try await NotionMCPConnector.shared.syncMemories(markdown: markdown)

    let detail = "Updated Notion page"
    persistStatus(
      destination: .notion,
      exportedCount: memories.count,
      detailText: detail,
      filePath: nil
    )
    return MemoryExportResult(
      memoryCount: memories.count,
      detailText: detail,
      destinationURL: pageURL,
      fileURL: nil,
      clipboardText: nil
    )
  }
}
