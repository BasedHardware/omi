import Foundation
import OmiTheme
import SwiftUI

/// Pure collapsed-body policy so the transcript's truncation contract can be
/// covered without requiring a running SwiftUI window.
enum ChatBubbleTruncation {
  static let threshold = 500

  static func shouldTruncate(text: String, isStreaming: Bool, isExpanded: Bool) -> Bool {
    !isStreaming && text.count > threshold && !isExpanded
  }

  static func displayText(_ text: String, isStreaming: Bool, isExpanded: Bool) -> String {
    guard shouldTruncate(text: text, isStreaming: isStreaming, isExpanded: isExpanded) else {
      return text
    }
    return String(text.prefix(threshold)).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
  }
}

/// Shared understated date treatment for a transcript row and its prompt-rail
/// preview. Keeping this outside the bubble makes the time contextual rather
/// than part of the message itself.
struct ChatMessageTimestamp: View {
  let date: Date

  var body: some View {
    Text(date, format: .dateTime.year().month(.abbreviated).day().hour().minute())
      .scaledFont(size: OmiType.micro)
      .foregroundColor(OmiColors.textTertiary.opacity(0.82))
  }
}

/// Visibility rule for the quiet timeline's per-message metadata row
/// (rating / copy / info / timestamp). Keyboard parity is part of the
/// contract: focus on any metadata control must reveal the row, otherwise
/// Tab / Full Keyboard Access ends up on an invisible button.
enum ChatBubbleMetadataReveal {
  static func isVisible(hovering: Bool, controlFocused: Bool, transientFeedback: Bool) -> Bool {
    hovering || controlFocused || transientFeedback
  }
}

struct BackgroundAgentSummary: Equatable {
  let agentID: UUID?
  let prompt: String
  let output: String

  static func parse(_ text: String) -> BackgroundAgentSummary? {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("[Background agent") else { return nil }
    guard let close = trimmed.firstIndex(of: "]") else { return nil }

    let headerStart = trimmed.index(trimmed.startIndex, offsetBy: 1)
    let header = String(trimmed[headerStart..<close])
    guard header.hasPrefix("Background agent") else { return nil }

    var remainder = String(header.dropFirst("Background agent".count))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    var agentID: UUID?

    if remainder.hasPrefix("id=") {
      remainder.removeFirst(3)
      let idEnd = remainder.firstIndex { $0 == " " || $0 == "—" } ?? remainder.endIndex
      let idText = String(remainder[..<idEnd]).trimmingCharacters(in: .whitespacesAndNewlines)
      agentID = UUID(uuidString: idText)
      remainder = String(remainder[idEnd...]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    if remainder.hasPrefix("—") {
      remainder.removeFirst()
      remainder = remainder.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    let outputStart = trimmed.index(after: close)
    let output = String(trimmed[outputStart...]).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !output.isEmpty else { return nil }

    return BackgroundAgentSummary(
      agentID: agentID,
      prompt: remainder.isEmpty ? "Background agent" : remainder,
      output: output
    )
  }
}
