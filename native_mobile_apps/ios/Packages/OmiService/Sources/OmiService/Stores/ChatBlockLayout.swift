import Foundation
import OmiCore

/// How a message's `content_blocks` sit against its body. Pure rules, so they are tested without
/// a screen: which blocks draw a card the user can act on, whether those cards replace the body
/// (a turn whose whole text is the fallback synthesized from its blocks) and, when they do,
/// which lines still have to be drawn so nothing on the wire is silently lost.
///
/// Mirrors Flutter `ChatContentBlockList` and `ServerMessage.textIsStructuredFallback`.
public enum ChatBlockLayout {
    /// A block with a component of its own. Everything else (text, thinking, tool calls,
    /// citations, a type this client does not know) has no card and shows its fallback line
    /// only when the cards replace the body, where the body can no longer carry it.
    public static func isRenderable(_ kind: ChatBlock.Kind) -> Bool {
        switch kind {
        case .task, .goal, .memory, .conversation, .discovery, .question, .agentRun, .memoryReview:
            true
        case .text, .other:
            false
        }
    }

    public static func hasRenderable(_ blocks: [ChatBlock]) -> Bool {
        blocks.contains { isRenderable($0.kind) }
    }

    /// True when the blocks carry the turn's whole content: only then do they replace the body.
    /// A review card is chrome (Flutter `MemoryReviewCard`), never a body of its own, so a turn
    /// that is nothing but a review card keeps whatever body it came with.
    private static func carriesBody(_ blocks: [ChatBlock]) -> Bool {
        blocks.contains { if case .memoryReview = $0.kind { false } else { isRenderable($0.kind) } }
    }

    /// The line each block would say as plain text, in order, as one body. This is what a client
    /// that cannot draw a block writes into the message text, and so what a body has to match to
    /// be nothing but that projection.
    public static func structuredFallback(_ blocks: [ChatBlock]) -> String {
        blocks.map(\.fallbackText).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
    }

    /// True when the body carries nothing of its own: it is empty, or exactly the fallback
    /// synthesized from the blocks. The cards then replace it instead of repeating it.
    ///
    /// A day summary keeps its body: it is a list, not a projection of blocks. A message with no
    /// body and no renderable block keeps the ordinary path, so a text-only turn is unaffected.
    public static func blocksReplaceBody(_ message: ChatMessage) -> Bool {
        guard message.kind != .daySummary, carriesBody(message.blocks) else { return false }
        let body = normalized(message.text)
        guard !body.isEmpty else { return true }
        let fallback = normalized(structuredFallback(message.blocks))
        return !fallback.isEmpty && body == fallback
    }

    /// The lines the cards cannot draw, so a body-replacing turn still shows them. A renderable
    /// block is its card; everything else is its fallback text.
    public static func fallbackLines(_ blocks: [ChatBlock]) -> [String] {
        blocks
            .filter { !isRenderable($0.kind) }
            .map(\.fallbackText)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private static func normalized(_ text: String) -> String {
        text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
}

/// A day summary is a list of what happened, not prose: Flutter `DaySummaryWidget.splitMessage`.
/// Numbered items lose their numbers ("1. …"), everything else splits at sentence ends.
public enum ChatDaySummary {
    public static func items(_ text: String) -> [String] {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }
        if trimmed.range(of: #"(?m)^\d+\.\s"#, options: .regularExpression) != nil {
            let withoutNumbers = trimmed.replacingOccurrences(
                of: #"\d+\.\s"#, with: "", options: .regularExpression
            )
            return withoutNumbers
                .components(separatedBy: CharacterSet(charactersIn: "\n."))
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        }
        return trimmed
            .components(separatedBy: ". ")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .map { $0.hasSuffix(".") ? String($0.dropLast()) : $0 }
            .filter { !$0.isEmpty }
    }
}
