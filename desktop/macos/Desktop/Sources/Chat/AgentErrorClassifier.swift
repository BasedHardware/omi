import Foundation

/// Bounded classification for free-form agent error strings.
///
/// PostHog telemetry may only carry bounded dimensions (never raw exception
/// text), and users may only be told "try again" when retrying can actually
/// help. This classifier is the single source for both: the 30-day
/// `chat_agent_error` corpus showed the opaque "Something went wrong. Please
/// try again." bucket was dominated by unretryable causes (exhausted provider
/// credits alone produced retry storms of 30+ events/day from single users).
enum AgentErrorCode: String, CaseIterable, Sendable {
  case providerBillingExhausted = "provider_billing_exhausted"
  case providerAuthExpired = "provider_auth_expired"
  case oauthTimeout = "oauth_timeout"
  case connectionFailed = "connection_failed"
  case payloadTooLarge = "payload_too_large"
  case runtimeCrashed = "runtime_crashed"
  case runtimeInstallIncomplete = "runtime_install_incomplete"
  case toolSchemaRejected = "tool_schema_rejected"
  case providerRateLimited = "provider_rate_limited"
  case providerOverloaded = "provider_overloaded"
  case localDataError = "local_data_error"
  case credentialLeakSuspected = "credential_leak_suspected"
  case planLimitReached = "plan_limit_reached"
  case agentModeUnavailable = "agent_mode_unavailable"
  case upstreamProviderFailed = "upstream_provider_failed"
  case userInterrupted = "user_interrupted"
  case unknown
}

struct ClassifiedAgentError: Equatable, Sendable {
  let code: AgentErrorCode
  let userMessage: String
  let retryable: Bool
}

enum AgentErrorClassifier {
  /// Single copy for an install whose agent runtime payload is incomplete.
  /// Owned here because this classifier is also the round-trip target: surfaces
  /// re-classify already-classified messages, so the phrase in the copy has to
  /// be the same phrase the rule matches.
  static let runtimeInstallIncompleteMessage =
    "Omi's local AI runtime is not installed correctly, so chat can't start. "
    + "Reinstall or update Omi to repair it."

  /// Worker recycle rewrites `userMessage` to "send again" while leaving the
  /// provider's 402 on `technicalMessage`. Classify both or the billing rule
  /// never fires and the transcript falls through to the unclassified marker.
  static func classify(_ failure: AgentRuntimeFailure) -> ClassifiedAgentError {
    classify(
      [failure.technicalMessage, failure.userMessage]
        .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
        .joined(separator: "\n")
    )
  }

  // ponytail: ordered substring rules over the observed error corpus; a rule
  // table beats ML until the corpus outgrows it. First match wins.
  static func classify(_ rawMessage: String) -> ClassifiedAgentError {
    let lower = rawMessage.lowercased()

    // User pressed Stop — not a technical failure. Recognized so it is never
    // mislabeled as a retryable error (the #1 string in the live corpus, 616
    // events/30d); upstream telemetry should also split it from chat_agent_error.
    if lower.hasPrefix("response stopped") {
      return ClassifiedAgentError(
        code: .userInterrupted,
        userMessage: "Response stopped.",
        retryable: false)
    }
    // Plan/usage cap — retrying just re-hits the cap (measured retry storms in
    // the live corpus). Direct to upgrade/reset, never "try again".
    if lower.contains("free plan limit") || lower.contains("plan and usage")
      || (lower.contains("plan limit") && lower.contains("upgrade"))
    {
      return ClassifiedAgentError(
        code: .planLimitReached,
        userMessage:
          "You've reached your plan's chat limit. Upgrade in Settings → Plan and Usage, or wait until the next reset.",
        retryable: false)
    }
    // Provider/mode configuration mismatch — retrying the same query cannot
    // help; the user must change the agent mode/provider in Settings.
    if lower.contains("only when the user claude mode")
      || lower.contains("can only use omi cloud routing")
      || lower.contains("provider mode is pinned")
      || (lower.contains("is not available") && lower.contains("make sure"))
    {
      return ClassifiedAgentError(
        code: .agentModeUnavailable,
        userMessage:
          "This agent isn't available in your current setup. Open Settings → check your agent mode/provider, then try again.",
        retryable: false)
    }

    // A bundle that shipped without its agent runtime payload fails identically
    // on every turn, so "the AI engine restarted, try again" is the wrong copy —
    // that phrasing produced retry loops against a permanently broken install.
    // Matched before the generic "process exited" rule below, which pi-mono's
    // own rejection string (`pi-mono process exited (code 1)`) would otherwise
    // claim. Also recognizes this classifier's own output so surfaces that
    // re-classify an already-classified message stay on the same code.
    if lower.contains("local ai runtime is not installed correctly")
      || lower.contains("extension path does not exist")
      || lower.contains("failed to load extension")
      || (lower.contains("unknown provider") && lower.contains("omi"))
    {
      return ClassifiedAgentError(
        code: .runtimeInstallIncomplete,
        userMessage: runtimeInstallIncompleteMessage,
        retryable: false)
    }

    // Omi's own desktop chat backend reports every upstream failure as the
    // fixed string "Upstream provider error" with code 502, delivered as an SSE
    // error frame inside an HTTP 200 body. The corpus had no rule for it, so it
    // fell through to `unknown` and the transcript showed the generic "Omi
    // couldn't answer this one" — which is what users saw for ~19 hours during
    // the 2026-08-20 gateway-parameter outage, with nothing on screen
    // indicating the failure was ours rather than their message.
    //
    // Retryable: the backend emits this for transient gateway conditions
    // (circuit open, transport failure, upstream timeout) as well as hard
    // rejections, and it does not distinguish them on the wire. Resending is
    // worth one attempt.
    if lower.contains("upstream provider error") {
      return ClassifiedAgentError(
        code: .upstreamProviderFailed,
        userMessage:
          "Omi's AI service didn't respond. This is on our side, not your message. "
          + "Try again in a moment.",
        retryable: true)
    }

    // The Omi-account proxy answers an exhausted billing lane with a bare 402
    // and no body, so the raw transport string ("HTTP 402 status code (no
    // body)") fell through to `unknown` and was shown verbatim — and, worse,
    // marked retryable, which is the retry storm this classifier exists to
    // prevent. Payment Required is never fixed by resending the same message.
    // Matched on status shape rather than a bare `402` so a token count or cost
    // that happens to contain those digits cannot claim this rule.
    if lower.contains("payment required")
      || lower.range(of: #"\bhttp[\s/]*402\b"#, options: .regularExpression) != nil
      || lower.range(
        of: #"\b(?:402\s+status|status(?:\s+code)?\s*[:=]?\s*402)\b"#,
        options: .regularExpression) != nil
    {
      return ClassifiedAgentError(
        code: .providerBillingExhausted,
        userMessage:
          "Omi's AI service declined this request for billing reasons. "
          + "Check Settings → Plan and Usage; resending the same message won't help.",
        retryable: false)
    }
    if lower.contains("credit balance is too low") {
      return ClassifiedAgentError(
        code: .providerBillingExhausted,
        userMessage:
          "Your Anthropic credit balance is too low. Add credits in your Anthropic account (Plans & Billing), then send your message again.",
        retryable: false)
    }
    if lower.contains("oauth callback timed out") {
      return ClassifiedAgentError(
        code: .oauthTimeout,
        userMessage: "Sign-in timed out. Open Settings and reconnect your account.",
        retryable: false)
    }
    // Only high-signal leak tokens belong here — providers say "leaked",
    // "invalid key", or "has been disabled" when a key is compromised. Generic
    // "forbidden"/"permission denied" are ordinary 403 authorization failures,
    // not leaks; classing them here both mislabels the user copy and gets the
    // event dropped by SentryBeforeSendPolicy (it filters "ai service
    // authentication error"), hiding real forbidden-class bugs from triage.
    if lower.contains("leaked") || lower.contains("invalid key") || lower.contains("has been disabled") {
      return ClassifiedAgentError(
        code: .credentialLeakSuspected,
        userMessage: "AI service authentication error. Please update the app to the latest version.",
        retryable: false)
    }
    if lower.contains("invalid_token") || lower.contains("authentication_error")
      || lower.contains("failed to authenticate") || lower.contains("unauthorized")
      || lower.contains("authentication required") || lower.contains("byok_validation_failed")
      || lower.contains("forbidden") || lower.contains("permission denied")
      || lower.contains("api key") || lower.contains("api_key")
    {
      return ClassifiedAgentError(
        code: .providerAuthExpired,
        userMessage: "Your AI session expired. Reconnect your account in Settings, then try again.",
        retryable: false)
    }
    if lower.contains("connection error") || lower.contains("econnrefused") || lower.contains("etimedout")
      || lower.contains("socket hang up") || lower.contains("network is unreachable")
    {
      return ClassifiedAgentError(
        code: .connectionFailed,
        userMessage: "Couldn't reach the AI service — check your internet connection and try again.",
        retryable: true)
    }
    if lower.contains("length limit exceeded") || lower.contains("payload too large")
      || lower.range(of: #"\b413\b"#, options: .regularExpression) != nil
    {
      return ClassifiedAgentError(
        code: .payloadTooLarge,
        userMessage:
          "That message or its attachments are too large to send. Try a smaller attachment or a shorter message.",
        retryable: false)
    }
    if lower.contains("process exited") || lower.contains("process not running") || lower.contains("terminated") {
      return ClassifiedAgentError(
        code: .runtimeCrashed,
        userMessage: "The AI engine restarted unexpectedly. Try sending your message again.",
        retryable: true)
    }
    if lower.contains("input_schema does not support") || lower.contains("tool_choice")
      || lower.contains("tool names must be unique") || lower.contains("tools must have unique names")
    {
      return ClassifiedAgentError(
        code: .toolSchemaRejected,
        userMessage:
          "A connected tool is misconfigured — this isn't caused by your message. Retrying won't help until the tool is fixed; the error has been recorded.",
        retryable: false)
    }
    if lower.contains("rate limit") || lower.contains("quota") || lower.contains("resource exhausted")
      || lower.contains("429")
    {
      return ClassifiedAgentError(
        code: .providerRateLimited,
        userMessage: "AI service is busy. Please try again in a moment.",
        retryable: true)
    }
    if lower.contains("overloaded") || lower.contains("service unavailable")
      || lower.contains("temporarily unavailable") || lower.contains("internal error")
      || lower.contains("529")
    {
      return ClassifiedAgentError(
        code: .providerOverloaded,
        userMessage: "AI service is temporarily unavailable. Please try again later.",
        retryable: true)
    }
    if lower.contains("transaction within a transaction") || lower.contains("database disk image")
      || lower.contains("database is locked") || lower.contains("no column named")
      || lower.contains("no such column") || lower.contains("no such table")
    {
      return ClassifiedAgentError(
        code: .localDataError,
        userMessage: "Omi hit a local data error. Restarting the app usually fixes this — your data is safe.",
        retryable: false)
    }

    // Unknown: keep the original message when it exists (many provider errors
    // are already user-readable); only truly empty errors get the generic copy.
    let fallback = rawMessage.isEmpty ? "Something went wrong. Please try again." : rawMessage
    return ClassifiedAgentError(code: .unknown, userMessage: fallback, retryable: true)
  }
}
