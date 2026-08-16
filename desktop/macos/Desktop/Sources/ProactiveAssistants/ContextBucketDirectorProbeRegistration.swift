#if DEBUG
  import Foundation

  extension DesktopAutomationActionRegistry {
    func registerContextBucketDirectorProbe() {
      register(
        name: "probe_context_bucket_director",
        summary: "Replay a synthetic context bucket through the director model boundary without delivery",
        params: [
          "bucket_id", "version", "header", "frozen", "tail", "validated_facts", "tasks", "app", "window",
          "captured_at", "notify_worthiness", "visit_count",
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
      registerProactiveCaptureStatusSnapshot()
    }
  }
#else
  extension DesktopAutomationActionRegistry {
    func registerContextBucketDirectorProbe() {}
  }
#endif
