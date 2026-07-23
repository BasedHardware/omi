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
  case toolSchemaRejected = "tool_schema_rejected"
  case providerRateLimited = "provider_rate_limited"
  case providerOverloaded = "provider_overloaded"
  case localDataError = "local_data_error"
  case credentialLeakSuspected = "credential_leak_suspected"
  case planLimitReached = "plan_limit_reached"
  case agentModeUnavailable = "agent_mode_unavailable"
  case userInterrupted = "user_interrupted"
  case unknown
}

struct ClassifiedAgentError: Equatable, Sendable {
  let code: AgentErrorCode
  let userMessage: String
  let retryable: Bool
}

enum AgentErrorClassifier {
  // ponytail: ordered substring rules over the observed error corpus; a rule
  // table beats ML until the corpus outgrows it. First match wins.
  static func classify(_ rawMessage: String) -> ClassifiedAgentError {
    let lower = rawMessage.lowercased()

    // User pressed Stop — not a technical failure. Recognized so it is never
    // mislabeled as a retryable error (the #1 string in the live corpus, 616
    // events/30d); upstream telemetry should also split it from chat_agent_error.
    if lower == "response stopped." || lower.hasPrefix("response stopped") {
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
    if lower.contains("length limit exceeded") || lower.contains("request body") && lower.contains("413")
      || lower.contains("413 ")
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
