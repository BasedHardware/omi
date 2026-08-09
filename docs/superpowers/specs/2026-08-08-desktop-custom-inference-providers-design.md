# Desktop Custom Inference Providers — design

**Date:** 2026-08-08
**Status:** proposed
**Surface:** macOS desktop (`desktop/macos`), Omi AI text and agent inference

## Outcome

Omi for Mac lets a user create an OpenAI-compatible inference connection and assign
its model to each text-inference level used by Omi AI. A connection consists of a
compatibility preset, display name, base URL, API key, model ID, context/output limits,
and declared capabilities. The initial presets are Generic OpenAI-Compatible, Z.AI,
Kimi/Moonshot, and DeepSeek; the generic preset keeps the feature open to providers
that Omi does not know by name.

Users can independently assign a connection/model to three levels:

1. **Fast** — frequent, latency-sensitive text and structured-output work such as
   live suggestions, grading, and lightweight extraction.
2. **Standard** — synthesis, memory/task/insight extraction, proactive analysis, and
   other background reasoning.
3. **Reasoning & agents** — Main Chat, floating chat, task chat, onboarding chat,
   delegated agents, tool loops, and explicit higher-model escalation.

Each level defaults to **Omi managed**, preserving current behavior for users who do
not configure anything. An expandable workload list allows a user to override an
individual workload when the three-level mapping is too coarse. The resolver therefore
supports every inventoried Mac text-inference call site without forcing a user to
configure each call site separately.

Custom inference applies only when the agent runtime is **Omi AI** (`piMono`). Claude,
Hermes, and OpenClaw remain external runtimes that own their own provider configuration.

## Scope boundary

This change covers text/chat-completions inference, including streaming, tool calling,
structured output, and image input where the configured model declares support.

It does not configure:

- embeddings or vector search;
- speech-to-text;
- realtime speech-to-speech;
- text-to-speech;
- image generation;
- server-side post-processing that runs after the Mac is offline.

Those surfaces use different protocols, lifecycles, and availability requirements.
Calling all of them “providers” in one form would create fields that are valid for only
some modalities and would falsely imply that a text model can replace Deepgram,
Gemini Live, or GPT Realtime. They should get separate modality-specific designs if
customization is required later.

The existing four-key BYOK free-plan contract also remains unchanged. Custom inference
and subscription entitlement are separate: a user may direct Mac text inference to a
custom provider while Omi still pays for managed transcription, realtime voice, or
server processing. The UI must not claim that one custom LLM key activates the free
plan.

## Current architecture and failure

The current UI and runtime conflate three different concepts:

- `AIProvider` and `ChatProvider.BridgeMode` select an **agent runtime**: Omi AI,
  Claude, Hermes, or OpenClaw.
- `ModelQoS` selects hardcoded **model IDs** for Claude and Gemini workloads.
- `BYOKProvider` stores a fixed **billing credential bundle** for OpenAI, Anthropic,
  Gemini, and Deepgram.

The inference backend is still fixed after the user chooses a runtime. `ModelQoS`
allows only one Claude model in its picker, the Pi adapter maps Claude IDs to the
hardcoded `omi` provider, and `pi-mono-extension` always calls Omi's managed gateway.
Proactive/background consumers separately construct Gemini-specific requests. A user
cannot express the actual route they want: “use this base URL, this credential, and
this model for this class of work.”

The kernel correctly makes execution profiles immutable per session, but the profile
contains only adapter and model. Reusing `adapterId`, `providerBoundary`, or a decorated
model string for an inference vendor would corrupt that ownership model:

- adapter identity answers which runtime executes the work;
- provider boundary answers whether that runtime is Omi-managed or local-user-owned;
- inference route answers where that runtime sends model requests.

The new design adds the missing typed inference-route reference instead of overloading
an existing field.

## Approaches considered

### A. Local compatibility-aware inference routing — selected

The Mac stores provider metadata locally, stores API keys in Keychain, validates route
capabilities, and calls the configured endpoint directly. Swift workloads use a shared
OpenAI-compatible client. Omi AI's bundled Pi extension dynamically registers the same
connections and selects the provider/model pinned in the kernel session profile.

This satisfies arbitrary-provider support, keeps credentials off Omi's backend, and
gives all Mac text inference one routing authority.

### B. Proxy arbitrary endpoints through Omi's backend — rejected

This would centralize transport, but it would send the user's API key through Omi and
let a client ask the backend to connect to an arbitrary URL. Making that safe requires
an endpoint allowlist or a substantial SSRF/egress policy, either of which defeats the
open custom-provider requirement. It also contradicts the existing “keys stay on this
Mac” promise.

### C. Hardcode Z.AI, Kimi, and DeepSeek — rejected

Provider-specific enum cases and fields are quick to add, but they repeat the current
catalog lock under three new names. Every new provider or endpoint variant would need
an app release. Presets belong in a compatibility layer over a generic connection,
not in the domain model.

## Provider compatibility contract

Version 1 supports the OpenAI Chat Completions protocol. “OpenAI-compatible” is a wire
family, not a guarantee of identical behavior, so a connection selects one preset:

| Preset | Default base URL | Required request behavior |
|---|---|---|
| Generic OpenAI-Compatible | user supplied | Standard Chat Completions roles, streaming, tools, and response format only when declared |
| Z.AI | `https://api.z.ai/api/paas/v4` | Preserve reasoning content through tool turns; support the provider's `thinking` body only when reasoning is enabled |
| Kimi / Moonshot | `https://api.moonshot.ai/v1` | Standard OpenAI tool-call streaming assembly; do not assume provider-hosted tools |
| DeepSeek | `https://api.deepseek.com` | Preserve reasoning content; omit unsupported `developer` role and `tool_choice` where the selected model requires it; use the provider-compatible token field |

Preset defaults are editable because providers expose region, coding-plan, and other
endpoint variants. A preset is a request/response normalization strategy, not a network
allowlist.

Version 1 deliberately omits arbitrary custom headers and custom request templates.
Both are secret-leak and support surfaces. Bearer API-key authentication covers the
named providers and the common compatible-provider case. A future authentication type
must be added as a typed strategy with redaction and tests.

## Domain model

### Stored provider configuration

`InferenceProviderConfiguration` is non-secret and Codable. Its identity includes the
revision so two immutable revisions of one logical connection never collide in SwiftUI
or persistence:

```swift
struct InferenceProviderRevisionID: Codable, Hashable, Sendable {
  let providerID: UUID
  let revision: Int
}

struct InferenceProviderConfiguration: Codable, Identifiable, Equatable, Sendable {
  let id: InferenceProviderRevisionID
  var displayName: String
  var preset: InferenceCompatibilityPreset
  var baseURL: URL
  var modelID: String
  var contextWindow: Int
  var maxOutputTokens: Int
  var capabilities: Set<InferenceCapability>
  var isEnabled: Bool
}
```

`InferenceCapability` contains `text`, `streaming`, `tools`, `structuredOutput`,
`imageInput`, and `reasoning`. Text is mandatory. Capability declarations are locally
validated and then proved by the connection test for any level that needs them.

The API key is never encoded with this structure. It is stored with
`DesktopKeychainStore` under a team-and-bundle-scoped service and an account derived
from the provider revision ID. Key rotation therefore creates a new credential item
instead of changing the key beneath a pinned session. Keychain unavailable is a
first-class state; the app preserves the prior credential on a failed update and never
falls back to UserDefaults.

### Routing assignments

`InferenceLevel` contains `fast`, `standard`, and `reasoningAgent`.
`InferenceWorkload` inventories every in-tree Mac text-inference purpose and declares:

- its default level;
- required capabilities;
- its current Omi-managed route.

`InferenceRouteSelection` is either `.omiManaged` or
`.custom(providerID: UUID, revision: Int)`. Settings persist one selection per level
and optional selections per workload. Resolution order is workload override, level
selection, then Omi managed.

`ResolvedInferenceRoute` is an immutable, non-secret value containing preset, base URL,
model ID, limits, capabilities, provider ID, and revision. The API key is fetched from
Keychain only at dispatch. Logs, telemetry, protocol messages, journal rows, and
snapshots may contain provider ID/preset/model and a key fingerprint, never the key.

## Components

### `InferenceConfigurationStore`

A `@MainActor` observable store owns provider configurations and assignments. The
structured non-secret payload is versioned and persisted in UserDefaults, matching
other desktop settings while avoiding a second database authority. Mutations validate
the complete new snapshot before one write and publish one change notification.

Provider revisions are immutable once referenced by an agent session. Editing a
connection creates its next revision. Disabled historical revisions stay available to
already-pinned sessions but cannot be selected for new work. Deletion is permitted
only when no persisted session references the revision; otherwise the UI offers to
migrate those sessions first. This preserves the kernel's immutable-profile contract.

### `InferenceRouteResolver`

The resolver is the sole workload-to-route authority. It rejects missing configuration,
missing credentials, disabled routes, stale revisions, invalid URLs, and capability
mismatches before a prompt is sent. It returns typed errors suitable for settings and
chat error cards.

Managed-default resolution retains the current per-workload Claude/Gemini choices; the
three user-facing levels do not collapse Omi's existing managed models into one model.
Only a custom assignment overlays those defaults.

### `OpenAICompatibleInferenceClient`

A shared Swift client accepts provider-neutral messages, content parts, tools,
structured-output schemas, streaming callbacks, and reasoning intent. A preset adapter
normalizes the request and response. It owns:

- URL and redirect validation;
- bearer authentication;
- bounded request/first-byte/idle deadlines;
- SSE assembly, including fragmented tool calls and reasoning content;
- bounded provider error parsing with no raw response logging;
- cancellation and exactly one terminal result.

Only HTTPS endpoints are allowed, except HTTP loopback (`localhost`, `127.0.0.0/8`,
and `::1`) for local inference servers. URLs with embedded credentials, fragments, or
non-HTTP schemes are rejected. Every redirect is revalidated and cannot downgrade
HTTPS or leave the original host unless the user explicitly tests and saves the final
URL as the connection endpoint.

### Swift workload migration

All text-inference consumers of `ModelQoS.Claude` and `ModelQoS.Gemini` move to an
`InferenceWorkload` lookup. Omi-managed calls retain their existing transports.
Custom routes use `OpenAICompatibleInferenceClient` directly. The change migrates all
text callers in one PR and removes the retired hardcoded `ModelQoS` selection API; no
alias or fallback compatibility layer remains. The excluded embedding constant moves
beside `EmbeddingService` as a managed modality-specific setting rather than being
misrepresented as a configurable text workload.

Vision workloads can select only a route that declares and passes image-input
validation. A text-only custom Standard route does not silently send a screenshot to
Omi managed inference. The UI either requires a workload override or reports the
incompatible assignment.

### Agent runtime and kernel

The kernel execution profile gains a typed `inferenceRoute` projection containing
provider UUID, revision, and model ID. This field is independent of `adapterId` and
`providerBoundary`, is inherited by delegated child runs, and participates in the
same immutable profile-generation checks as adapter/model/cwd.

Swift supplies only configured route metadata and injects the selected revision's
credential into the local agent process at startup without logging it. The Pi extension
dynamically registers each enabled custom revision under a stable provider ID and the
Pi adapter sends `set_model` with both provider ID and model ID instead of hardcoding
`provider: "omi"`.

Changing a level affects future sessions. Settings offers an explicit “Apply to current
Omi AI chats” action that uses the existing user-requested profile migration path.
In-flight runs finish against their pinned generation; the runtime restarts only after
the migration boundary. External runtimes reject custom inference-route assignment.

## User experience

Settings gains an **Inference** subsection. The existing “AI Provider” label becomes
**Agent Runtime** so it no longer implies model-vendor selection.

The Inference subsection contains:

1. three level cards showing Omi managed or the selected connection/model;
2. a Connections list with Add, Edit, Test, Disable, and Delete actions;
3. an expandable Advanced Workload Overrides list;
4. a disclosure that prompts, images, tool schemas, and relevant Omi context are sent
   directly to the chosen provider;
5. a separate note that custom inference does not by itself activate Omi's free plan.

The connection editor asks for preset, name, base URL, API key, model ID, context
window, maximum output, and capabilities. Presets fill safe defaults but never lock
the fields. Save is disabled until URL and numeric validation pass. Assigning a route
to a level runs the capability-specific connection test first.

Provider model lists are not compiled into the app and are not treated as authoritative.
The user enters the exact model ID from their provider. An optional `/models` lookup may
suggest IDs when supported, but manual entry always remains available.

## Data flow

1. The user creates a connection. Non-secret metadata is validated in memory and the
   API key is written to Keychain.
2. Test Connection resolves the exact candidate without persisting an assignment and
   performs a minimal text request plus the capability probes required by the target
   level. A connection may also be saved unassigned after its basic text test passes.
3. On success, the store commits the provider revision. Assigning it to a level or
   workload is a separate validated snapshot mutation, so a failed assignment cannot
   leave a partially changed routing table.
4. A Swift workload asks the resolver for its `InferenceWorkload`. The resolver pins
   an Omi-managed route or the selected custom revision.
5. A direct Swift workload fetches the key and calls the shared client. An agent
   workload resolves or migrates a kernel session whose immutable profile carries the
   inference route.
6. Completion, failure, or cancellation flows through the existing workload owner.
   Provider routing never becomes a second chat or voice lifecycle owner.

## Failure and fallback policy

- Invalid URL, missing key, missing revision, and capability mismatch fail before
  dispatch with actionable settings guidance.
- A custom-provider 401/403 marks only that provider revision unhealthy through
  `CredentialHealthManager`; it never invalidates the Firebase session.
- A custom-provider quota/rate-limit error is visible as that provider's failure.
- No custom route silently falls back to Omi managed or to another custom provider.
  That could change cost, privacy, model behavior, and tool semantics without consent.
- Omi-managed routing keeps its existing server-owned resilience behavior.
- If an existing managed path changes provider or mode while recovering, it continues
  to use the shared fallback telemetry contract. A custom-route terminal failure is
  not mislabeled as a successful fallback.
- Provider response bodies, prompt text, base-URL paths, and keys never enter PostHog.
  Local logs contain bounded host/preset/model/status metadata only; Sentry receives a
  sanitized error class.

## Testing and verification

### Hermetic tests

- Configuration decoding, schema migration, atomic snapshot mutation, and corrupt
  payload recovery.
- Keychain account scoping, unavailable reads/writes, rotation, disable, and delete;
  assertions prove serialized settings and logs contain no API key.
- URL validation and redirect policy, including loopback HTTP and blocked downgrade,
  embedded credentials, fragments, non-loopback HTTP, and host-changing redirects.
- Resolver precedence and every workload's level/capability requirements.
- Preset request/response fixtures for Generic, Z.AI, Kimi, and DeepSeek, including
  fragmented streaming tool calls and reasoning-content replay.
- Connection probes for text, tools, structured output, and image input against a
  local fake OpenAI-compatible server.
- Kernel schema migration, route inheritance, stale generation rejection, explicit
  session migration, and external-runtime rejection.
- Pi extension dynamic registration and provider/model selection; a static guard
  rejects reintroduction of hardcoded `provider: "omi"` at the selection boundary.
- Behavioral Settings tests for create/edit/test/assign/disable/delete and secret
  redaction.
- A completeness guard requires every desktop text-inference call site to name an
  `InferenceWorkload` and prohibits production callers of the retired `ModelQoS`
  selection API.

### Real-path verification

1. Run the focused Swift and Node tests, the desktop test-quality check, and
   `./scripts/agent-logic-harness.sh --cross-surface-smoke`.
2. Launch `OMI_APP_NAME=omi-custom-inference ./run.sh` and configure the bundled local
   fake endpoint through the real Settings UI.
3. Exercise one Fast workload, one Standard workload, Main Chat with a tool call, a
   delegated agent, cancellation, an invalid key, and a capability mismatch. Confirm
   provider/model identity in bounded diagnostics and continuity in one chat timeline.
4. With a separately supplied test credential, run the same live text/tool smoke
   against at least one of Z.AI, Kimi, or DeepSeek. Never put that credential in a test
   fixture, command transcript, commit, or PR body.
5. Run the prompt gauntlet for tool compatibility, `./scripts/omi-macos-dev doctor`,
   the desktop component suite, `make preflight`, `scripts/pr-preflight --suggest`, and
   `scripts/pr-preflight --pr-body-file` before opening a PR.

## Documentation and release surface

- Update `desktop/macos/AGENTS.md` with the inference ownership and verification route.
- Update `docs/doc/developer/agent-control-plane.mdx` for the new immutable route field.
- Add a developer document describing provider presets, capability requirements,
  Keychain storage, direct-provider privacy, and the free-plan boundary.
- Add a user-visible changelog fragment.
- Run `scripts/pr-preflight --suggest` to discover all matched invariant IDs. INV-6
  continuity and the session-profile/kernel guards remain unchanged in meaning and
  gain coverage for the new route field.

## Rollout

The schema and UI ship together with all assignments defaulted to Omi managed. No
feature flag or dual path is needed: the new custom path is unreachable until a user
creates, tests, and assigns a connection. Existing sessions decode with a null custom
route and retain their managed profile. Custom-provider errors never alter server
traffic or Omi's managed gateway rollout.

## Implementation-agent model policy

The implementation plan assigns the least expensive capable Codex worker to each
reviewable task:

- `gpt-5.6-terra`, medium reasoning: settings UI, persistence, docs, consumer
  migrations, and routine behavioral tests.
- `gpt-5.6-sol`, medium reasoning: transport normalization, agent protocol/kernel
  schema, Pi provider selection, and cross-language contract work.
- `gpt-5.6-sol`, high reasoning: final security/privacy and full cross-surface review
  only.

No task defaults to `gpt-5.6-sol` high merely because it touches inference.

## External protocol references

- [Z.AI OpenAI SDK compatibility](https://docs.z.ai/guides/develop/openai/python)
- [Z.AI thinking and tool calling](https://docs.z.ai/guides/capabilities/thinking-mode)
- [Kimi API overview](https://platform.kimi.ai/docs/api/overview)
- [Kimi tool calls](https://platform.kimi.ai/docs/guide/use-kimi-api-to-complete-tool-calls)
- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls)
- [DeepSeek OpenAI compatibility notes](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/)
