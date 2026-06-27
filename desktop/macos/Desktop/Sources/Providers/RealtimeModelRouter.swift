import Foundation

// MARK: - RealtimeModelRouter
//
// Decides which model to use for the realtime voice (PTT) path. Mirrors
// `ChatModelRouter` exactly but uses the `.pttResponse` task type.
//
// Same fallback chain as ChatModelRouter:
//   1. If `selectedModel` is empty or "Auto" (case-insensitive):
//        - Try `AutoRouter.shared.currentPick(for: .pttResponse)`
//        - If non-nil, use it
//        - If nil, fall back to `fallback`
//   2. Otherwise: use the user's selected model directly
//
// The upstream `AutoModelSelector.refresh()` already calls
// `AutoRouter.shared.refreshIfStale(...)` for the realtime-voice task,
// so this router does NOT trigger refresh itself (the upstream code path
// is the entry point).

enum RealtimeModelSelectionReason: String {
    case userSelected
    case routerPick
    case routerFallback
}

enum RealtimeModelRouter {
    struct Decision {
        let model: String
        let reason: RealtimeModelSelectionReason
        let routerPick: String?
    }

    /// Returns the model to use for the realtime voice path.
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
