#if DEBUG
  import Foundation

  extension DesktopAutomationActionRegistry {
    func registerProactiveCaptureStatusSnapshot() {
      register(
        name: "proactive_capture_status_snapshot",
        effects: [],
        summary: "Read coarse screen-capture and context-bucket monitoring state without content",
        sideEffects: [
          "read-only local state",
          "does not capture a screenshot, call a model/backend, or deliver notifications",
          "does not expose app names, window titles, exact idle duration, or identities",
        ],
        examples: ["./scripts/omi-ctl action proactive_capture_status_snapshot"]
      ) { _ in
        ProactiveAssistantsPlugin.shared.automationCaptureStatusSnapshot().automationDetail
      }
    }
  }
#else
  extension DesktopAutomationActionRegistry {
    func registerProactiveCaptureStatusSnapshot() {}
  }
#endif
