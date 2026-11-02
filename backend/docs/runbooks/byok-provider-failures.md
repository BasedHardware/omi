# BYOK provider failures: what they look like in logs

A BYOK (bring-your-own-key) user's own provider account running out of credit,
hitting its usage limits, or carrying a rejected key is **user account state,
not an Omi server fault**. Every conversation-processing boundary answers these
as a typed 429 (`code: byok_quota` / `byok_rate_limit` / `byok_invalid_key`)
instead of the generic 500, and logs them at **WARNING**, never ERROR.

## Log shape

One structured line per failure, no traceback, no uid/key material beyond what
neighbouring lines already carry:

```
byok provider failure is user account state, not a server fault: byok=true failure_class=byok_quota provider=anthropic route=conversation_processing
```

- `failure_class` — `byok_quota` (credit/usage-limit/insufficient-quota, incl.
  Anthropic 400 "credit balance is too low" / "reached your specified API usage
  limits", OpenRouter 402 `openrouter_credits`, OpenAI 429 `insufficient_quota`),
  `byok_rate_limit` (the account's own rate limits), or `byok_invalid_key`
  (rejected key, incl. the gateway's `byok_auth`).
- `provider` — `anthropic`, `openai`, `openrouter`, or `gateway` (the failure
  was classified by the Omi gateway's own failure-class envelope).
- `route` — where the boundary saw it: `conversation_processing`,
  `conversation_processing/app_result`, `llm/<feature>` (LangChain error
  callback), `background_task/<name>` (executor failure funnel).

These are classified **only when the failing request ran on the user's own
validated key**. The same provider error on Omi's server-paid key stays a loud
ERROR and a generic 500 — that is a real server fault.

## Cloud Logging filter

Exclude them from severity>=ERROR investigations:

```
severity>=ERROR AND NOT textPayload:"byok=true"
```

(Backend serves in text mode today; once `OMI_LOG_FORMAT=json` is enabled for a
service, use `NOT jsonPayload.message:"byok=true"` there.)

## Metrics

`omi_capture_finalization_failures_total{reason="byok_provider"}` carries these
failures separately from `reason="provider"`/"processing"; dashboards and alerts
on server-fault counts should exclude that reason.

## Where the classifier lives

`utils/llm/gateway_error_contract.py` — `classify_byok_provider_failure` (the
single classifier) and `conversation_processing_http_exception` (the
conversation-processing composition boundary). New provider spellings are added
there, never as a parallel classifier.
