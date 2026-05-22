import AppKit
import Foundation

@MainActor
final class OmiContextResolver {
    static let shared = OmiContextResolver()
    private init() {}

    /// Resolves all {{variable}} tokens in step values.
    /// - transcript: the user's PTT voice transcript for this session
    /// Returns a new OmiWorkflowPlan with all variables substituted.
    func resolve(_ plan: OmiWorkflowPlan, transcript: String) -> OmiWorkflowPlan {
        let selection = axSelectedText()
        let resolvedSelection = selection.isEmpty
            ? (NSPasteboard.general.string(forType: .string) ?? "")
            : selection

        let variables: [String: String] = [
            "{{selection}}": resolvedSelection,
            "{{clipboard}}": NSPasteboard.general.string(forType: .string) ?? "",
            "{{transcript}}": transcript,
            "{{app}}": NSWorkspace.shared.frontmostApplication?.localizedName ?? "",
        ]

        let resolvedSteps = plan.steps.map { step -> OmiWorkflowStep in
            var resolvedValue = step.value
            if var v = resolvedValue {
                for (token, replacement) in variables {
                    v = v.replacingOccurrences(
                        of: token,
                        with: replacement,
                        options: .caseInsensitive
                    )
                }
                resolvedValue = v
            }
            return OmiWorkflowStep(
                action: step.action,
                target: step.target,
                value: resolvedValue,
                scrollDirection: step.scrollDirection,
                scrollAmount: step.scrollAmount,
                stepDescription: step.stepDescription
            )
        }

        return OmiWorkflowPlan(description: plan.description, steps: resolvedSteps)
    }

    private func axSelectedText() -> String {
        let system = AXUIElementCreateSystemWide()
        var focusedRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(system, kAXFocusedUIElementAttribute as CFString, &focusedRef) == .success,
              let focusedRef = focusedRef else { return "" }
        let axElement = focusedRef as! AXUIElement
        var selRef: CFTypeRef?
        guard AXUIElementCopyAttributeValue(axElement, kAXSelectedTextAttribute as CFString, &selRef) == .success,
              let sel = selRef as? String, !sel.isEmpty else { return "" }
        return sel
    }
}
