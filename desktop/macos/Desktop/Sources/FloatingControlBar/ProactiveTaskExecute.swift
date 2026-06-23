import Foundation

/// Prompt fragments for proactive task notification actions.
///
/// The floating-bar agent normally lives under `floatingBarSystemPromptPrefix`,
/// which tells it to answer in 1-2 sentences and never ask follow-ups. That's
/// too brief when the user explicitly asks for help with a task - the user
/// needs reviewable preparation, not silent external action.
///
/// `systemPromptSuffix` is appended after the main system prompt so it takes
/// precedence over the floating-bar concise-answer rules, and `buildQuery`
/// frames the prompt as preparation for review.
enum ProactiveTaskExecute {

    /// Restatement of the task. Tells the agent to prepare the next step for
    /// review before anything externally visible or destructive happens.
    static func buildQuery(title: String, message: String) -> String {
        """
        Prepare this task for review.

        Task: \(title)
        Details: \(message)

        Use available Omi context to draft, summarize, gather facts, or outline
        the safest next action. Do not send, post, update, delete, create
        external records, change files, or claim completion without explicit
        user confirmation in an approved flow.
        """
    }

    /// Appended to the system prompt for proactive task pills only. Overrides
    /// the floating-bar "1-2 sentence concise answer" stance so Omi can prepare
    /// enough context for the user to review and confirm.
    static let systemPromptSuffix = """
================================================================================
PREPARE MODE - OVERRIDES the floating-bar "concise answer" rules above
================================================================================
The user wants Omi to prepare the next step from context, then let them review
before anything is sent or changed.

Use available read-only context as needed: memories, conversations, action
items, files, and app facts that Omi already has access to. You may draft,
summarize, compare options, identify missing facts, or propose the next action.

Do not send messages, post content, edit external systems, delete anything,
create records, schedule events, change files, or claim the task is completed
from this pill. If the next step needs an externally visible or destructive
action, prepare the draft or checklist and state what the user should review
and confirm.

Trust model: suggest, prepare, confirm, act. This response is the preparation
step. Keep the user in control.

FINAL REPORT FORMAT: one concise paragraph with what you prepared and what the
user should review next. No headers, no long lists.
================================================================================
"""
}
