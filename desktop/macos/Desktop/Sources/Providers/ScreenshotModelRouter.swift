import Foundation

// MARK: - ScreenshotModelRouter
//
// Decides which model to use for screenshot understanding (vision-language
// analysis of screen captures). Mirrors `ChatModelRouter` but for the
// `.screenshotUnderstanding` task type.
//
// Same fallback chain:
//   1. If `selectedVisionModel` is empty or "Auto" → use router pick
//   2. Otherwise → use the user's selected vision model
//   3. Fallback: a default vision model if no router pick is cached

enum ScreenshotModelSelectionReason: String {
    case userSelected
    case routerPick
    case routerFallback
}

enum ScreenshotModelRouter {
    struct Decision {
        let model: String
        let reason: ScreenshotModelSelectionReason
        let routerPick: String?
    }

    /// Returns the model to use for screenshot understanding.
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
