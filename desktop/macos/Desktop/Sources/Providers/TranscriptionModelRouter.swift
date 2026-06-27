import Foundation

// MARK: - TranscriptionModelRouter
//
// Decides which STT model to use for transcription. Mirrors `ChatModelRouter`
// but for the `.transcription` task type.
//
// Same fallback chain:
//   1. If `selectedSTTModel` is empty or "Auto" → use router pick
//   2. Otherwise → use the user's selected STT model
//   3. Fallback: a default STT model if no router pick is cached

enum TranscriptionModelSelectionReason: String {
    case userSelected
    case routerPick
    case routerFallback
}

enum TranscriptionModelRouter {
    struct Decision {
        let model: String
        let reason: TranscriptionModelSelectionReason
        let routerPick: String?
    }

    /// Returns the model to use for transcription.
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
