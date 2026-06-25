import Foundation

// MARK: - EmbeddingModelRouter
//
// Decides which embedding model to use for the screenshot embedding
// pipeline. Mirrors `ChatModelRouter` but for the `.screenshotEmbedding`
// task type.
//
// Same fallback chain:
//   1. If `selectedEmbeddingModel` is empty or "Auto" → use router pick
//   2. Otherwise → use the user's selected embedding model
//   3. Fallback: a default embedding model if no router pick is cached

enum EmbeddingModelSelectionReason: String {
    case userSelected
    case routerPick
    case routerFallback
}

enum EmbeddingModelRouter {
    struct Decision {
        let model: String
        let reason: EmbeddingModelSelectionReason
        let routerPick: String?
    }

    /// Returns the model to use for screenshot embedding.
    static func decide(
        selectedModel: String?,
        routerPick: String?,
        fallback: String
    ) -> Decision {
        let trimmed = (selectedModel ?? "").trimmingCharacters(in: .whitespaces)
        let isAutoOrEmpty = trimmed.isEmpty || trimmed.lowercased() == "auto"

        if isAutoOrEmpty {
            if let pick = routerPick?.trimmingCharacters(in: .whitespaces), !pick.isEmpty {
                return Decision(model: pick, reason: .routerPick, routerPick: routerPick)
            }
            return Decision(model: fallback, reason: .routerFallback, routerPick: routerPick)
        }
        return Decision(model: trimmed, reason: .userSelected, routerPick: routerPick)
    }
}
