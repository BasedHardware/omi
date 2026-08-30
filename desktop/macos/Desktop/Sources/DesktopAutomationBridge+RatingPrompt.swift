import Foundation

/// Rating-prompt automation actions: inspect and drive the one-time
/// "rate Omi Desktop" bar without cursor clicks. `rating_prompt_submit`
/// goes through the same `RatingPromptManager.submit` the star buttons call,
/// so exercising it covers the production path.
extension DesktopAutomationActionRegistry {
  func registerRatingPromptActions() {
    register(
      name: "rating_prompt_state",
      summary: "Return the rating prompt's persisted trigger state and visibility"
    ) { _ in
      await MainActor.run {
        let manager = RatingPromptManager.shared
        return [
          "schema": "visible,question_count,submitted_rating,dismissed,thank_you",
          "visible": manager.isVisible ? "true" : "false",
          "question_count": "\(manager.questionCount)",
          "submitted_rating": "\(manager.submittedRating)",
          "dismissed": manager.isDismissed ? "true" : "false",
          "thank_you": "\(manager.thankYouRating ?? 0)",
          "remotely_disabled": manager.isRemotelyDisabled ? "true" : "false",
          "comment_pending": "\(manager.commentPendingScore ?? 0)",
          "config_enabled": manager.config.enabled ? "true" : "false",
          "config_threshold": "\(manager.config.questionThreshold)",
          "config_comment_max_score": "\(manager.config.commentMaxScore)",
          "config_revision": "\(manager.config.revision)",
        ]
      }
    }

    register(
      name: "rating_prompt_submit",
      summary: "Submit a 1-5 star rating through the same path as the star buttons",
      params: ["rating"]
    ) { params in
      let rating = params["rating"].flatMap { Int($0) } ?? 5
      return await MainActor.run {
        let manager = RatingPromptManager.shared
        guard manager.isVisible else {
          return ["submitted": "false", "reason": "prompt not visible"]
        }
        manager.submit(rating: rating)
        if let pending = manager.commentPendingScore {
          // Low score: nothing is submitted yet — the comment step is next.
          return ["submitted": "false", "comment_pending": "\(pending)"]
        }
        return ["submitted": "true", "rating": "\(manager.submittedRating)"]
      }
    }

    register(
      name: "rating_prompt_submit_comment",
      summary: "Send the pending low-score comment through the same path as the Send button (empty comment = Skip)",
      params: ["comment"]
    ) { params in
      let comment = params["comment"] ?? ""
      return await MainActor.run {
        let manager = RatingPromptManager.shared
        guard let score = manager.commentPendingScore else {
          return ["submitted": "false", "reason": "no comment pending"]
        }
        manager.submitPendingComment(comment)
        return ["submitted": "true", "rating": "\(score)", "comment": comment]
      }
    }

    register(
      name: "rating_prompt_record_question",
      summary:
        "Count one asked question through RatingPromptManager.recordQuestionAsked — the exact call the chatMessageSent analytics funnel makes"
    ) { _ in
      await MainActor.run {
        RatingPromptManager.shared.recordQuestionAsked()
        let manager = RatingPromptManager.shared
        return [
          "question_count": "\(manager.questionCount)",
          "visible": manager.isVisible ? "true" : "false",
        ]
      }
    }

    register(
      name: "rating_prompt_refer",
      summary: "Trigger the thank-you bar's refer-a-friend proposal (same path as the button)"
    ) { _ in
      await MainActor.run {
        guard RatingPromptManager.shared.thankYouRating != nil else {
          return ["opened": "false", "reason": "no thank-you active"]
        }
        RatingPromptManager.shared.referFriend()
        return ["opened": "true"]
      }
    }

    register(
      name: "rating_prompt_seed",
      summary: "Run the history seed now (same call as app launch)"
    ) { _ in
      await RatingPromptManager.shared.seedFromHistoryIfNeeded()
      return await MainActor.run {
        let m = RatingPromptManager.shared
        return ["question_count": "\(m.questionCount)", "visible": m.isVisible ? "true" : "false"]
      }
    }

    register(
      name: "rating_prompt_reset",
      summary: "Reset persisted rating-prompt state so the trigger can be exercised again"
    ) { _ in
      await MainActor.run {
        RatingPromptManager.shared.resetForTesting()
        return ["reset": "true"]
      }
    }
  }
}
