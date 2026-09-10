import Foundation

extension DesktopAutomationActionRegistry {
  func registerPTTRecoveryActions() {
    register(
      name: "voice_typing_deliver_text",
      summary: "Verify dictation insertion with a supplied transcript (bypasses microphone and ASR, no network)",
      params: ["text"], category: "voice", surfaces: ["floating_bar"], safety: "local_ui_state"
    ) { params in
      guard AppBuild.isNonProduction else { return ["error": "non-production only"] }
      guard let text = params["text"], !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        return ["error": "text required"]
      }
      return await PushToTalkManager.shared.dictateForAutomation(
        pcm16k: Data(), allowNetwork: false, knownTranscript: "type " + text)
    }

    register(
      name: "voice_typing_undo",
      summary: "Invoke the guarded Undo Last Dictation action on the unchanged focused editor",
      category: "voice", surfaces: ["floating_bar"], safety: "local_ui_state"
    ) { _ in
      guard AppBuild.isNonProduction else { return ["error": "non-production only"] }
      return ["undone": PushToTalkManager.shared.undoLastDictation() ? "true" : "false"]
    }

    register(
      name: "ptt_recovery_snapshot",
      summary: "Report offline-question and guarded dictation-undo availability without text",
      category: "voice", surfaces: ["floating_bar"], safety: "read_only"
    ) { _ in
      guard AppBuild.isNonProduction else { return ["error": "non-production only"] }
      return [
        "question_available": OfflinePTTQuestionRecovery.shared.isAvailable ? "true" : "false",
        "undo_available": PushToTalkManager.shared.canUndoLastDictation ? "true" : "false",
      ]
    }

    register(
      name: "ptt_recovery_fixture",
      summary: "Stage a supplied offline question through the real recovery store; does not send or journal it",
      params: ["text"], category: "voice", surfaces: ["floating_bar"], safety: "local_ui_state"
    ) { params in
      guard AppBuild.isNonProduction else { return ["error": "non-production only"] }
      guard let text = params["text"],
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
        let owner = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
      else {
        return ["error": "text and a current authenticated owner required"]
      }
      let stored = OfflinePTTQuestionRecovery.shared.capture(text, authorization: owner)
      return ["question_available": stored ? "true" : "false"]
    }

    register(
      name: "ptt_recovery_review",
      summary: "Review the recovered offline question in the main composer without sending it",
      category: "voice", surfaces: ["main_chat"], safety: "local_ui_state"
    ) { _ in
      guard AppBuild.isNonProduction else { return ["error": "non-production only"] }
      OfflinePTTQuestionRecovery.shared.reviewInMainChat()
      return ["question_available": OfflinePTTQuestionRecovery.shared.isAvailable ? "true" : "false"]
    }
  }
}
