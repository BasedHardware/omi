#if DEBUG
  import Foundation

  extension DesktopAutomationActionRegistry {
    func registerContextBucketDirectorProbe() {
      register(
        name: "probe_context_bucket_director",
        summary: "Replay a synthetic context bucket through the director model boundary without delivery",
        params: [
          "bucket_id", "version", "header", "frozen", "tail", "validated_facts", "tasks", "app", "window",
          "captured_at", "notify_worthiness", "visit_count", "retrieved", "lookup_query",
        ],
        safety: "network_or_model",
        sideEffects: [
          "may call model/backend services",
          "eligible replays consume the signed-in account's proactivity reasoning quota",
          "does not write the database, change gates/settings, graduate tasks, or deliver notifications",
        ]
      ) { params in
        guard AppBuild.isNonProduction else {
          return ["error": "probe_context_bucket_director is disabled on production bundles"]
        }
        return try await ContextBucketDirectorProbe().run(params: params)
      }
      register(
        name: "probe_context_director_present",
        summary:
          "Present a director decision through the real notification presentation gate stack (QA of the delivery surface; pairs with probe_context_bucket_director)",
        params: ["title", "message", "decision_type", "detail"],
        safety: "ui",
        sideEffects: [
          "shows a real floating-bar/system notification to the signed-in owner",
          "subject to the same owner, category-toggle, and throttle gates as an organic delivery",
        ]
      ) { params in
        guard AppBuild.isNonProduction else {
          return ["error": "probe_context_director_present is disabled on production bundles"]
        }
        let title = params["title"] ?? ""
        let message = params["message"] ?? ""
        guard !title.isEmpty, !message.isEmpty else {
          return ["error": "title and message are required"]
        }
        let decisionType = params["decision_type"] ?? "insight"
        let detail = params["detail"] ?? ""
        return await MainActor.run {
          guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(), !ownerID.isEmpty else {
            return ["error": "no signed-in owner"]
          }
          let context = FloatingBarNotificationContext(
            sourceTitle: title,
            assistantId: "context-director",
            contextSummary: "probe_context_director_present replay",
            detail: detail,
            provenanceRef: "probe-present")
          let result = NotificationService.shared.presentContextDirectorNotification(
            ownerID: ownerID,
            title: title,
            message: message,
            decisionType: decisionType,
            context: context)
          return ["presentation": "\(result)"]
        }
      }
      registerProactiveCaptureStatusSnapshot()
    }
  }
#else
  extension DesktopAutomationActionRegistry {
    func registerContextBucketDirectorProbe() {}
  }
#endif
