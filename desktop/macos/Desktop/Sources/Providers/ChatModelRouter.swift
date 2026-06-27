import Foundation

// MARK: - ChatModelRouter
//
// Decides which model to use for the chat path. When the user has
// selected "Auto" (or no specific model), the router consults the
// auto-router for a per-task model pick. When the user has selected a
// specific model, that selection is used directly.
//
// This is the v2 wiring that connects the auto-router framework to
// the existing ChatProvider. v1 of the auto-router was a standalone
// framework with no production users; v2 is the first wired path.
//
// Why `currentPick` (not `pick`): currentPick is a sync UserDefaults
// read. pick() is async and would block chat init on a network call.
// The desktop client prefetches picks in the background (via
// `AutoRouter.shared.refreshIfStale(for: .generalAssistant)`).
//
// Fallback chain:
//   1. If `selectedModel` is empty or "Auto" (case-insensitive):
//        - Try `AutoRouter.shared.currentPick(for: .generalAssistant)`
//        - If non-nil, use it
//        - If nil, fall back to `ModelQoS.Claude.defaultSelection`
//   2. Otherwise: use the user's selected model directly
//
// No new behavior for users with a specific model selected. The
// auto-router only affects users who:
//   - Have never set a model (selectedModel == "")
//   - Have explicitly set "Auto"

enum ChatModelSelectionReason: String {
    /// User has a specific model selected — use it directly.
    case userSelected
    /// User has "Auto" or empty; router provided a cached pick.
    case routerPick
    /// User has "Auto" or empty; router has no cached pick yet.
    case routerFallback
}

enum ChatModelRouter {
    struct Decision {
        let model: String
        let reason: ChatModelSelectionReason
        let routerPick: String?
    }

    /// Returns the model to use for the chat path, with provenance.
    /// - Empty / "Auto" settings → use `routerPick` if non-nil
    /// - Specific model settings → use the user's choice
    /// - Falls back to `fallback` (default: `ModelQoS.Claude.defaultSelection`)
    ///
    /// The caller must fetch `routerPick` from `AutoRouter.shared.currentPick(for:)`
    /// on the @MainActor (the `currentPick` property is MainActor-isolated).
    /// This indirection keeps `decide` synchronous, pure, and testable
    /// without requiring the AutoRouter singleton.
    static func decide(
        selectedModel: String,
        routerPick: String?,
        fallback: String = ModelQoS.Claude.defaultSelection
    ) -> Decision {
        let trimmed = selectedModel.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty || trimmed.lowercased() == "auto" {
            // Trim routerPick too (cubic review): whitespace-only or unnormalized
            // values would otherwise be treated as valid model selections.
            let trimmedPick = routerPick?.trimmingCharacters(in: .whitespacesAndNewlines)
            if let pick = trimmedPick, !pick.isEmpty {
                return Decision(model: pick, reason: .routerPick, routerPick: pick)
            }
            return Decision(model: fallback, reason: .routerFallback, routerPick: nil)
        }
        return Decision(model: trimmed, reason: .userSelected, routerPick: nil)
    }
}
