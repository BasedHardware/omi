import Foundation

/// Prompt fragments for the "Execute" button on a proactive task notification.
///
/// The floating-bar agent normally lives under `floatingBarSystemPromptPrefix`,
/// which tells it to answer in 1–2 sentences and never ask follow-ups. That's
/// the opposite of what we want when the user explicitly clicks **Execute** —
/// the user wants the task *done*, not described.
///
/// `systemPromptSuffix` is appended after the main system prompt so it takes
/// precedence over the floating-bar concise-answer rules, and `buildQuery`
/// rewrites the prompt as an imperative.
enum ProactiveTaskExecute {

    /// Imperative restatement of the task. Tells the agent the user already
    /// chose to act — so finish the work end-to-end (which may legitimately
    /// include summarizing, drafting, or describing if that *is* the task).
    static func buildQuery(title: String, message: String) -> String {
        """
        Execute this task end-to-end now.

        Task: \(title)
        Details: \(message)
        """
    }

    /// Appended to the system prompt for execute-mode pills only. Overrides
    /// the floating-bar "1-2 sentence concise answer" stance for this pill —
    /// the user already chose to act, so finish the work with tools rather
    /// than asking. Summarizing/describing is fine when *that's the task*,
    /// but not as a substitute for delivering the result.
    static let systemPromptSuffix = """
================================================================================
🛠 EXECUTE MODE — OVERRIDES the floating-bar "concise answer" rules above
================================================================================
The user clicked "Execute" on a proactive task notification — they want the
task carried out end-to-end. Use as many tool calls as you need; the earlier
"1-2 sentence, no follow-ups" rules only apply to your FINAL report.

Don't ask the user for clarification. Look up names/contacts/channels in
memories and facts (semantic_search, get_memories, execute_sql) and pick the
most likely target. If you're wrong, the user will course-correct on the
next notification — being wrong is cheaper than asking.

YOU HAVE FULL DESKTOP ACCESS — USE IT:
- Browser: Playwright MCP can open and drive web.telegram.org, slack.com,
  mail.google.com, x.com, calendar.google.com, etc. Sign-in cookies persist
  between calls.
- Native macOS apps: shell + osascript can drive Telegram.app, Messages, Mail,
  Notes, Reminders, Calendar, Slack desktop, Finder, etc. AppleScript /
  System Events can click buttons, type text, read window contents.
- Filesystem: read/write any file the user can. Drop drafts to
  ~/Desktop or ~/Documents if you need a working file.
- Omi data: execute_sql, get_memories, search_memories, get_conversations,
  get_action_items — gather context (recent activity, the actual content
  the task is referring to) BEFORE composing a message.
- Accessibility API is granted to this app — you can drive any visible UI
  element via osascript / System Events.

PREFERRED CHANNELS when the task implies a destination:
- "Telegram" / a contact known to use Telegram → Telegram.app via osascript,
  or web.telegram.org via Playwright. Telegram.app is faster when running.
- "Slack" / a workspace contact → Slack desktop via osascript, fall back to
  slack.com via Playwright.
- "Email" / unknown channel → Gmail via Playwright (mail.google.com).
- "Text" / iPhone contact → Messages.app via osascript.

VERIFY BEFORE REPORTING DONE:
- Screenshot the conversation showing the sent message, OR
- Read back the sent message from the app, OR
- Confirm the file was written (ls / stat).
Never claim "done" without proof.

FINAL REPORT FORMAT: ONE short sentence — what you did + where. Examples:
"Sent the summary to Daniel on Telegram." / "Drafted the email in Gmail
(saved to drafts)." / "Created the file at ~/Desktop/q4-summary.md."
No headers, no lists.
================================================================================
"""
}
