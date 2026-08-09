# Desktop Custom Inference Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Omi for Mac users configure arbitrary OpenAI-compatible text-inference providers and assign their models independently to Fast, Standard, and Reasoning & Agents workloads.

**Architecture:** Add a local, Keychain-backed inference configuration authority and a provider-neutral route resolver. Direct Swift workloads use a shared OpenAI-compatible client; Omi AI agent sessions persist an independent inference-route reference through the Swift/Node kernel contract, and the bundled Pi extension dynamically registers the selected provider/model. Omi-managed routes remain the default and custom-route failures never silently cross back to managed inference.

**Tech Stack:** Swift 6/SwiftUI/Foundation/Security, TypeScript/Node/Vitest/SQLite, bundled `@earendil-works/pi-coding-agent`, existing desktop automation and named-bundle harnesses.

## Global Constraints

- Support macOS 14.0 and newer; do not raise the deployment floor.
- Add no production dependency. Use Foundation networking and `DesktopKeychainStore`.
- Cover Mac text/chat-completions inference only: text, streaming, tools, structured output, reasoning content, and optional image input.
- Do not route embeddings, STT, realtime voice, TTS, image generation, or offline server jobs through this feature.
- Keep Claude, Hermes, and OpenClaw runtime-owned inference unchanged; custom routes apply to Omi AI (`piMono`).
- Keep the existing four-key BYOK/free-plan contract unchanged and clearly separate from custom inference.
- Store non-secret settings locally; store every API key in a revision-scoped Keychain item. Never persist a key in UserDefaults, SQLite, logs, telemetry, fixtures, or protocol messages.
- Call custom endpoints directly from the Mac. Never forward their URLs or keys through Omi's backend.
- Permit HTTPS endpoints and HTTP loopback only. Revalidate redirects; reject credentials in URLs, fragments, non-HTTP schemes, HTTPS downgrade, and host-changing redirects.
- A custom-route failure is terminal and visible. Never silently fall back to Omi managed or a different custom provider.
- Preserve immutable kernel execution profiles, provider-boundary ownership, child inheritance, chat continuity (INV-6), and the Firebase-vs-provider 401 boundary.
- Migrate all in-tree text callers in the same PR and remove the retired hardcoded `ModelQoS` selection API; do not leave aliases or dual routing paths.
- Never use purple in the UI. Add a user-facing changelog fragment.
- All tests are hermetic unless explicitly identified as named-bundle or credentialed live verification.

## Codex Worker Allocation

| Task | Worker | Reasoning | Why |
|---|---|---:|---|
| 1. Configuration, Keychain, endpoint policy | `gpt-5.6-terra` | medium | Bounded Swift domain/storage work with explicit security tests |
| 2. OpenAI-compatible transport and presets | `gpt-5.6-sol` | medium | Provider protocol normalization and streaming/tool-call edge cases |
| 3. Workload inventory and route resolver | `gpt-5.6-terra` | medium | Typed routing policy and exhaustive mapping |
| 4. Direct Swift workload migration | `gpt-5.6-terra` | medium | Mostly mechanical consumer migration behind tested seams |
| 5. Kernel execution-profile contract | `gpt-5.6-sol` | medium | Cross-language immutable profile and SQLite migration |
| 6. Dynamic Pi provider registration | `gpt-5.6-sol` | medium | Secret injection plus provider/model selection across Swift and Node |
| 7. Chat and agent surface wiring | `gpt-5.6-sol` | medium | Cross-surface session pinning, migration, and continuity |
| 8. Settings and automation UI | `gpt-5.6-terra` | medium | SwiftUI composition and behavioral automation |
| 9. Documentation and complete verification | `gpt-5.6-terra` | medium | Docs, commands, and evidence collection |
| Final independent review | `gpt-5.6-sol` | high | One security/privacy/cross-surface audit only |

Do not substitute `gpt-5.6-sol` high for routine implementation tasks.

## File Structure

### New Swift production files

- `desktop/macos/Desktop/Sources/Inference/InferenceModels.swift` — provider revisions, capabilities, levels, selections, route references, and typed errors.
- `desktop/macos/Desktop/Sources/Inference/InferenceEndpointPolicy.swift` — URL normalization and redirect admission.
- `desktop/macos/Desktop/Sources/Inference/InferenceCredentialStore.swift` — revision-scoped Keychain access.
- `desktop/macos/Desktop/Sources/Inference/InferenceConfigurationStore.swift` — versioned non-secret snapshot and validated mutations.
- `desktop/macos/Desktop/Sources/Inference/InferenceProviderPresetAdapter.swift` — Generic/Z.AI/Kimi/DeepSeek request and response normalization.
- `desktop/macos/Desktop/Sources/Inference/OpenAICompatibleInferenceClient.swift` — request execution, cancellation, deadlines, and terminal results.
- `desktop/macos/Desktop/Sources/Inference/OpenAICompatibleSSEDecoder.swift` — bounded streaming delta/tool/reasoning assembly.
- `desktop/macos/Desktop/Sources/Inference/InferenceWorkload.swift` — exhaustive workload catalog and managed defaults.
- `desktop/macos/Desktop/Sources/Inference/InferenceRouteResolver.swift` — workload/level/override resolution.
- `desktop/macos/Desktop/Sources/Inference/InferenceDispatchService.swift` — managed-vs-custom dispatch for non-agent Swift workloads.
- `desktop/macos/Desktop/Sources/Inference/InferenceConnectionProbe.swift` — minimal text and capability probes.
- `desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+Inference.swift` — level cards, connections, editor, disclosure, and workload overrides.

### New test files

- `desktop/macos/Desktop/Tests/InferenceConfigurationStoreTests.swift`
- `desktop/macos/Desktop/Tests/InferenceEndpointPolicyTests.swift`
- `desktop/macos/Desktop/Tests/InferenceCredentialStoreTests.swift`
- `desktop/macos/Desktop/Tests/InferenceProviderPresetAdapterTests.swift`
- `desktop/macos/Desktop/Tests/OpenAICompatibleInferenceClientTests.swift`
- `desktop/macos/Desktop/Tests/OpenAICompatibleSSEDecoderTests.swift`
- `desktop/macos/Desktop/Tests/InferenceRouteResolverTests.swift`
- `desktop/macos/Desktop/Tests/InferenceWorkloadCompletenessTests.swift`
- `desktop/macos/Desktop/Tests/InferenceSettingsTests.swift`
- `desktop/macos/Desktop/Tests/InferenceAgentRouteTests.swift`
- `desktop/macos/e2e/fixtures/fake_openai_compatible_provider.py`
- `desktop/macos/agent/tests/custom-inference-route.test.ts`
- `desktop/macos/agent/tests/custom-inference-provider.test.ts`
- `desktop/macos/pi-mono-extension/custom-provider.test.ts`

### Principal modified files

- `desktop/macos/Desktop/Sources/ModelQoS.swift` — delete after all text callers migrate; move the excluded embedding default beside `EmbeddingService`.
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/Desktop/Sources/Chat/AgentClient.swift`
- `desktop/macos/Desktop/Sources/Chat/AgentRuntimeProcess.swift`
- `desktop/macos/Desktop/Sources/Chat/AgentRuntimePayload.swift`
- `desktop/macos/Desktop/Sources/ProactiveAssistants/Core/GeminiClient.swift`
- every production file currently returned by `rg -l 'ModelQoS\.' desktop/macos/Desktop/Sources`.
- `desktop/macos/Desktop/Sources/MainWindow/Pages/SettingsPage.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+Advanced.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+FloatingBarAndChat.swift`
- `desktop/macos/Desktop/Sources/DesktopAutomationBridge.swift`
- `desktop/macos/agent/src/protocol.ts`
- `desktop/macos/agent/src/runtime/types.ts`
- `desktop/macos/agent/src/runtime/sqlite-store.ts`
- `desktop/macos/agent/src/runtime/session-execution-profile.ts`
- `desktop/macos/agent/src/runtime/kernel-runs.ts`
- `desktop/macos/agent/src/runtime/kernel-support.ts`
- `desktop/macos/agent/src/runtime/jsonl-transport.ts`
- `desktop/macos/agent/src/adapters/interface.ts`
- `desktop/macos/agent/src/adapters/pi-mono.ts`
- `desktop/macos/pi-mono-extension/index.ts`
- `desktop/macos/e2e/flows/ai-chat-settings.yaml`
- `desktop/macos/AGENTS.md`
- `docs/doc/developer/agent-control-plane.mdx`

---

### Task 1: Revisioned Configuration, Keychain Storage, and Endpoint Admission

**Execution model:** `gpt-5.6-terra`, medium reasoning

**Files:**
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceModels.swift`
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceEndpointPolicy.swift`
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceCredentialStore.swift`
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceConfigurationStore.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceConfigurationStoreTests.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceEndpointPolicyTests.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceCredentialStoreTests.swift`

**Interfaces:**
- Produces: `InferenceProviderRevisionID`, `InferenceProviderConfiguration`, `InferenceCapability`, `InferenceLevel`, `InferenceWorkloadID`, `InferenceRouteSelection`, `InferenceRouteRef`, `InferenceConfigurationSnapshot`, `InferenceConfigurationStore`, `InferenceCredentialStoring`, and `InferenceEndpointPolicy`.
- Persistence key: `desktopInferenceConfiguration.v1`.
- Keychain service base: `com.omi.desktop.custom-inference` through `DesktopKeychainStore.scopedService`.
- Keychain account: `<provider UUID lowercase>:r<positive revision>`.

- [ ] **Step 1: Write model, snapshot, and corruption-recovery tests**

```swift
@MainActor
final class InferenceConfigurationStoreTests: XCTestCase {
  func testDefaultSnapshotUsesManagedRouteAtEveryLevel() throws {
    let store = InferenceConfigurationStore(defaults: isolatedDefaults(), credentials: FakeInferenceCredentials())
    XCTAssertEqual(store.snapshot.schemaVersion, 1)
    XCTAssertEqual(store.snapshot.levelAssignments[.fast], .omiManaged)
    XCTAssertEqual(store.snapshot.levelAssignments[.standard], .omiManaged)
    XCTAssertEqual(store.snapshot.levelAssignments[.reasoningAgent], .omiManaged)
  }

  func testCorruptPayloadRecoversManagedWithoutOverwritingEvidence() throws {
    let defaults = isolatedDefaults()
    defaults.set(Data("not-json".utf8), forKey: InferenceConfigurationStore.storageKey)
    let store = InferenceConfigurationStore(defaults: defaults, credentials: FakeInferenceCredentials())
    XCTAssertEqual(store.snapshot, .managedDefault)
    XCTAssertNotNil(defaults.data(forKey: InferenceConfigurationStore.corruptBackupKey))
  }

  func testEditingCreatesNewImmutableRevision() throws {
    let store = makeStore()
    let first = try store.addProvider(.zaiFixture)
    let second = try store.reviseProvider(first.id, changes: .init(modelID: "glm-5.1"))
    XCTAssertEqual(second.id.providerID, first.id.providerID)
    XCTAssertEqual(second.id.revision, first.id.revision + 1)
    XCTAssertNotNil(store.configuration(for: first.id))
  }
}
```

- [ ] **Step 2: Write endpoint-policy tests before implementation**

```swift
func testEndpointPolicyAllowsHTTPSAndLoopbackHTTPOnly() throws {
  XCTAssertEqual(try InferenceEndpointPolicy.normalize(URL(string: "https://api.z.ai/api/paas/v4/")!).absoluteString,
                 "https://api.z.ai/api/paas/v4")
  XCTAssertNoThrow(try InferenceEndpointPolicy.normalize(URL(string: "http://127.0.0.1:11434/v1")!))
  XCTAssertThrowsError(try InferenceEndpointPolicy.normalize(URL(string: "http://deepseek.example/v1")!))
  XCTAssertThrowsError(try InferenceEndpointPolicy.normalize(URL(string: "https://key@example.com/v1")!))
  XCTAssertThrowsError(try InferenceEndpointPolicy.normalize(URL(string: "file:///tmp/provider")!))
}

func testRedirectCannotChangeHostOrDowngradeTLS() throws {
  let original = URL(string: "https://api.moonshot.ai/v1/chat/completions")!
  XCTAssertNoThrow(try InferenceEndpointPolicy.admitRedirect(from: original, to: original.appending(queryItems: [])))
  XCTAssertThrowsError(try InferenceEndpointPolicy.admitRedirect(
    from: original, to: URL(string: "http://api.moonshot.ai/v1/chat/completions")!))
  XCTAssertThrowsError(try InferenceEndpointPolicy.admitRedirect(
    from: original, to: URL(string: "https://attacker.example/v1/chat/completions")!))
}
```

- [ ] **Step 3: Write Keychain wrapper tests with an injected backend**

```swift
func testCredentialAccountIsRevisionScopedAndNeverSerialized() throws {
  let backend = FakeKeychainBackend()
  let store = InferenceCredentialStore(backend: backend, teamID: "TEAM", bundleID: "com.omi.test")
  let id = InferenceProviderRevisionID(providerID: UUID(uuidString: "11111111-1111-1111-1111-111111111111")!, revision: 2)
  XCTAssertTrue(store.set("secret-value", for: id))
  XCTAssertEqual(store.read(id), .found("secret-value"))
  XCTAssertEqual(backend.lastAccount, "11111111-1111-1111-1111-111111111111:r2")
  XCTAssertFalse(String(data: try JSONEncoder().encode(InferenceConfigurationSnapshot.managedDefault), encoding: .utf8)!.contains("secret"))
}
```

- [ ] **Step 4: Run the new tests and confirm red failures**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'Inference(ConfigurationStore|EndpointPolicy|CredentialStore)Tests'
```

Expected: FAIL because the `Inference` production types do not exist.

- [ ] **Step 5: Implement the domain types and strict invariants**

```swift
enum InferenceCompatibilityPreset: String, Codable, CaseIterable, Sendable {
  case genericOpenAI, zai, kimi, deepSeek
}

enum InferenceCapability: String, Codable, CaseIterable, Hashable, Sendable {
  case text, streaming, tools, structuredOutput, imageInput, reasoning
}

struct InferenceProviderRevisionID: Codable, Hashable, Sendable {
  let providerID: UUID
  let revision: Int
}

enum InferenceRouteSelection: Codable, Equatable, Sendable {
  case omiManaged
  case custom(InferenceProviderRevisionID)
}

struct InferenceConfigurationSnapshot: Codable, Equatable, Sendable {
  let schemaVersion: Int
  var providers: [InferenceProviderConfiguration]
  var levelAssignments: [InferenceLevel: InferenceRouteSelection]
  var workloadOverrides: [InferenceWorkloadID: InferenceRouteSelection]

  static let managedDefault = InferenceConfigurationSnapshot(
    schemaVersion: 1,
    providers: [],
    levelAssignments: [.fast: .omiManaged, .standard: .omiManaged, .reasoningAgent: .omiManaged],
    workloadOverrides: [:])
}
```

Reject empty names/model IDs, nonpositive revisions, context windows outside `1_024...2_000_000`, output limits outside `1...262_144`, configurations without `.text`, duplicate revision IDs, unknown assignment IDs, and more than 32 retained revisions.

- [ ] **Step 6: Implement endpoint and credential policies**

`InferenceEndpointPolicy.normalize(_:)` returns a URL without trailing slash and rejects the invalid classes covered above. `admitRedirect(from:to:)` requires matching lowercase host and effective port, matching scheme, and another complete `normalize` pass.

`InferenceCredentialStore` adapts this testable protocol to `DesktopKeychainStore`:

```swift
protocol InferenceCredentialStoring: Sendable {
  func read(_ id: InferenceProviderRevisionID) -> DesktopKeychainStore.ReadResult
  @discardableResult func set(_ value: String, for id: InferenceProviderRevisionID) -> Bool
  func delete(_ id: InferenceProviderRevisionID)
}
```

- [ ] **Step 7: Implement validated snapshot mutations**

`InferenceConfigurationStore` must build and validate a complete candidate snapshot before one `UserDefaults.set(Data, forKey:)`. A failed mutation leaves the published snapshot unchanged. A new provider writes its Keychain credential first; if snapshot persistence fails, delete only that new revision's item. Revising never deletes the previous revision or key.

- [ ] **Step 8: Run focused tests and desktop quality checks**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'Inference(ConfigurationStore|EndpointPolicy|CredentialStore)Tests'
python3 scripts/check_desktop_test_quality.py
```

Expected: PASS, with no source-inspection or wall-clock baseline increase.

- [ ] **Step 9: Commit the storage boundary**

```bash
git add desktop/macos/Desktop/Sources/Inference desktop/macos/Desktop/Tests/InferenceConfigurationStoreTests.swift desktop/macos/Desktop/Tests/InferenceEndpointPolicyTests.swift desktop/macos/Desktop/Tests/InferenceCredentialStoreTests.swift
git commit -m "feat(desktop): add custom inference configuration store"
```

---

### Task 2: OpenAI-Compatible Transport and Compatibility Presets

**Execution model:** `gpt-5.6-sol`, medium reasoning

**Files:**
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceProviderPresetAdapter.swift`
- Create: `desktop/macos/Desktop/Sources/Inference/OpenAICompatibleInferenceClient.swift`
- Create: `desktop/macos/Desktop/Sources/Inference/OpenAICompatibleSSEDecoder.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceProviderPresetAdapterTests.swift`
- Test: `desktop/macos/Desktop/Tests/OpenAICompatibleInferenceClientTests.swift`
- Test: `desktop/macos/Desktop/Tests/OpenAICompatibleSSEDecoderTests.swift`
- Create fixtures: `desktop/macos/Desktop/Tests/fixtures/inference/{generic,zai,kimi,deepseek}-*.json`

**Interfaces:**
- Consumes: `InferenceProviderConfiguration`, `InferenceCapability`, and `InferenceEndpointPolicy` from Task 1.
- Produces: `InferenceRequest`, `InferenceMessage`, `InferenceTool`, `InferenceEvent`, `InferenceUsage`, `InferenceTerminalResult`, `InferenceProviderPresetAdapting`, and `OpenAICompatibleInferenceClient.stream`.

- [ ] **Step 1: Write preset normalization tests from checked-in provider fixtures**

```swift
func testDeepSeekPresetRemovesDeveloperRoleAndUnsupportedToolChoice() throws {
  let request = fixtureRequest(role: .developer, toolChoice: .automatic, reasoning: .high)
  let body = try DeepSeekPresetAdapter().encode(request, model: "deepseek-v4-pro")
  XCTAssertEqual(body.messages.first?.role, "system")
  XCTAssertNil(body.toolChoice)
  XCTAssertEqual(body.maxTokens, 256)
}

func testZAIAndDeepSeekPreserveReasoningContentAcrossToolTurn() throws {
  for adapter in [ZAIPresetAdapter(), DeepSeekPresetAdapter()] as [InferenceProviderPresetAdapting] {
    let messages = try adapter.decodeAndAppendToolTurn(fixtureNamed: "reasoning-tool-call")
    XCTAssertEqual(messages[1].reasoningContent, "bounded reasoning fixture")
  }
}

func testKimiAssemblesFragmentedStreamingToolArguments() throws {
  let events = try decodeFixture("kimi-streaming-tool-call")
  XCTAssertEqual(events.compactMap(\.toolCallDelta).map(\.argumentsFragment).joined(), #"{"city":"Paris"}"#)
}
```

- [ ] **Step 2: Write transport terminal-state and redaction tests**

```swift
func testClientProducesExactlyOneTerminalEvent() async throws {
  let transport = StubInferenceTransport(chunks: successSSEChunks)
  let events = try await collect(OpenAICompatibleInferenceClient(transport: transport).stream(fixtureRoute, request: .hello))
  XCTAssertEqual(events.filter(\.isTerminal).count, 1)
}

func testCancellationDoesNotEmitFailureAfterCancelled() async throws {
  let transport = SuspendedInferenceTransport()
  let task = Task { try await collect(makeClient(transport).stream(fixtureRoute, request: .hello)) }
  task.cancel()
  let events = try await task.value
  XCTAssertEqual(events.last, .cancelled)
}

func testProviderErrorIsBoundedAndDoesNotExposeBodyOrKey() async throws {
  let secret = "never-log-this"
  let error = await executeFailure(status: 401, body: Data(repeating: 65, count: 32_000), apiKey: secret)
  XCTAssertEqual(error.failureClass, .providerAuthentication)
  XCTAssertLessThan(error.userMessage.utf8.count, 512)
  XCTAssertFalse(error.diagnostic.contains(secret))
  XCTAssertFalse(error.diagnostic.contains(String(repeating: "A", count: 100)))
}
```

- [ ] **Step 3: Run the transport tests and confirm red failures**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'InferenceProviderPresetAdapterTests|OpenAICompatible(InferenceClient|SSEDecoder)Tests'
```

Expected: FAIL because the client and preset adapters do not exist.

- [ ] **Step 4: Implement provider-neutral request and event types**

```swift
struct InferenceRequest: Sendable {
  let messages: [InferenceMessage]
  let tools: [InferenceTool]
  let responseSchema: InferenceJSONSchema?
  let reasoning: InferenceReasoningIntent?
  let maxOutputTokens: Int
  let stream: Bool
}

enum InferenceEvent: Equatable, Sendable {
  case textDelta(String)
  case reasoningDelta(String)
  case toolCallDelta(InferenceToolCallDelta)
  case completed(InferenceTerminalResult)
  case cancelled

  var isTerminal: Bool {
    switch self {
    case .completed, .cancelled: return true
    default: return false
    }
  }
}
```

The preset protocol must be pure and fixture-testable:

```swift
protocol InferenceProviderPresetAdapting: Sendable {
  func encode(_ request: InferenceRequest, model: String) throws -> OpenAIChatCompletionBody
  func decodeDelta(_ json: Data) throws -> [InferenceEvent]
}
```

- [ ] **Step 5: Implement the four preset strategies**

Generic emits only declared features. Z.AI adds `thinking: {"type":"enabled"}` for non-nil reasoning and preserves `reasoning_content`. Kimi uses standard OpenAI tool deltas. DeepSeek rewrites `developer` to `system`, omits unsupported `tool_choice`, uses `max_tokens`, and preserves `reasoning_content`. Keep model-specific switches in the DeepSeek preset table, not scattered call sites.

- [ ] **Step 6: Implement the bounded SSE decoder**

Bound individual SSE lines to 1 MiB, aggregate tool arguments to 4 MiB per call, reject more than 128 simultaneous tool calls, ignore `[DONE]` only after flushing the last decoded event, and never decode a partial UTF-8 sequence as replacement text. Preserve tool-call index/id/name across fragments.

- [ ] **Step 7: Implement the client and redirect delegate**

```swift
protocol InferenceStreamingTransport: Sendable {
  func stream(_ request: URLRequest, redirectPolicy: InferenceEndpointPolicy) -> AsyncThrowingStream<Data, Error>
}

struct OpenAICompatibleInferenceClient: Sendable {
  func stream(
    route: ResolvedInferenceRoute,
    apiKey: String,
    request: InferenceRequest
  ) -> AsyncThrowingStream<InferenceEvent, Error>
}
```

Use `URLSession` with injected transport for tests, `Authorization: Bearer`, a 3-second connect timeout, a 25-second first-byte timeout, a 60-second silent-stream timeout, and request cancellation propagation. Classify 401/403, 429/quota, invalid request, timeout, transport interruption, capability mismatch, and malformed/oversized response without logging raw bodies.

- [ ] **Step 8: Run focused transport tests and formatting**

Run:

```bash
cd desktop/macos
./scripts/swift-format-wrapper.sh format -i Desktop/Sources/Inference Desktop/Tests/InferenceProviderPresetAdapterTests.swift Desktop/Tests/OpenAICompatibleInferenceClientTests.swift Desktop/Tests/OpenAICompatibleSSEDecoderTests.swift
xcrun swift test --package-path Desktop --filter 'InferenceProviderPresetAdapterTests|OpenAICompatible(InferenceClient|SSEDecoder)Tests'
```

Expected: PASS for all four presets, streaming, cancellation, limits, redirects, and redaction.

- [ ] **Step 9: Commit the transport**

```bash
git add desktop/macos/Desktop/Sources/Inference desktop/macos/Desktop/Tests/InferenceProviderPresetAdapterTests.swift desktop/macos/Desktop/Tests/OpenAICompatibleInferenceClientTests.swift desktop/macos/Desktop/Tests/OpenAICompatibleSSEDecoderTests.swift desktop/macos/Desktop/Tests/fixtures/inference
git commit -m "feat(desktop): add compatible inference transport"
```

---

### Task 3: Exhaustive Workload Catalog and Route Resolver

**Execution model:** `gpt-5.6-terra`, medium reasoning

**Files:**
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceWorkload.swift`
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceRouteResolver.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceRouteResolverTests.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceWorkloadCompletenessTests.swift`

**Interfaces:**
- Consumes: configuration snapshot and credentials from Task 1.
- Produces: `InferenceWorkload`, `ManagedInferenceRoute`, `ResolvedInferenceRoute`, `InferenceRouteResolving.resolve(workload:additionalCapabilities:)`.

- [ ] **Step 1: Write the full workload-policy test**

```swift
func testEveryWorkloadHasLevelManagedDefaultAndCapabilities() {
  for workload in InferenceWorkload.allCases {
    XCTAssertFalse(workload.requiredCapabilities.isEmpty)
    XCTAssertTrue(workload.requiredCapabilities.contains(.text))
    XCTAssertFalse(workload.managedDefault.modelID.isEmpty)
  }
  XCTAssertEqual(InferenceWorkload.suggestion.defaultLevel, .fast)
  XCTAssertEqual(InferenceWorkload.synthesis.defaultLevel, .standard)
  XCTAssertEqual(InferenceWorkload.mainChat.defaultLevel, .reasoningAgent)
}
```

The production enum is exact:

```swift
enum InferenceWorkload: String, Codable, CaseIterable, Sendable {
  case suggestion, chatLabGrade
  case synthesis, proactiveVision, taskExtraction, insight, chatLabQuery, contextVocabulary
  case mainChat, floatingChat, taskChat, onboardingChat, delegatedAgent, higherModel, memoryExportAgent
}
```

- [ ] **Step 2: Write resolver precedence, capability, and secret tests**

```swift
func testResolverUsesWorkloadOverrideBeforeLevelAssignment() throws {
  let resolver = makeResolver(level: .custom(zai), override: [.mainChat: .custom(deepSeek)])
  XCTAssertEqual(try resolver.resolve(.mainChat).revisionID, deepSeek)
}

func testResolverDoesNotFallbackWhenCustomRouteLacksTools() throws {
  let resolver = makeResolver(level: .custom(kimiTextOnly))
  XCTAssertThrowsError(try resolver.resolve(.mainChat)) { error in
    XCTAssertEqual(error as? InferenceRoutingError, .capabilityMismatch(required: [.streaming, .tools]))
  }
}

func testResolverReturnsNonSecretRoute() throws {
  let route = try makeResolver(level: .custom(zai)).resolve(.mainChat)
  XCTAssertFalse(String(describing: route).contains("test-api-key"))
}
```

- [ ] **Step 3: Run the resolver tests and confirm red failures**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'Inference(RouteResolver|WorkloadCompleteness)Tests'
```

Expected: FAIL because the workload catalog and resolver do not exist.

- [ ] **Step 4: Implement workload defaults and dynamic capabilities**

Map `suggestion` and `chatLabGrade` to Fast; synthesis/proactive/task/insight/ChatLab/context vocabulary to Standard; all chat/agent/higher-model/export work to Reasoning & Agents. Required capabilities are request-shape minimums; `resolve` unions image input or structured output supplied by the actual request before admission.

Managed defaults must reproduce current values from `ModelQoS` exactly, including distinct Gemini Flash/Pro behavior under the existing managed tier. Do not route managed defaults through the new custom transport.

- [ ] **Step 5: Implement deterministic resolution**

```swift
protocol InferenceRouteResolving: Sendable {
  func resolve(
    _ workload: InferenceWorkload,
    additionalCapabilities: Set<InferenceCapability>
  ) throws -> ResolvedInferenceRoute
}
```

Resolution order is workload override, level assignment, Omi managed. A custom result requires an exact retained revision, enabled-for-new-work status unless the caller supplies a pinned historical reference, a readable credential, and a superset of required capabilities. Return a typed error; do not catch-and-resolve managed.

- [ ] **Step 6: Add a typed workload-completeness guard**

In `InferenceWorkloadCompletenessTests`, assert that `InferenceWorkload.allCases` exactly matches the expected workload IDs and that each case has a level, managed default, and non-empty capability set. This guard passes before consumer migration and makes a newly added workload fail until its routing policy is declared. Task 7 owns the separate final source-inspection tripwire after `ModelQoS` is deleted. Behavioral resolver tests remain primary coverage.

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'Inference(RouteResolver|WorkloadCompleteness)Tests'
python3 scripts/check_desktop_test_quality.py
```

Expected: resolver and typed completeness tests PASS without depending on the Task 7 consumer migration.

- [ ] **Step 8: Commit the routing policy**

```bash
git add desktop/macos/Desktop/Sources/Inference/InferenceWorkload.swift desktop/macos/Desktop/Sources/Inference/InferenceRouteResolver.swift desktop/macos/Desktop/Tests/InferenceRouteResolverTests.swift desktop/macos/Desktop/Tests/InferenceWorkloadCompletenessTests.swift
git commit -m "feat(desktop): resolve inference by workload level"
```

---

### Task 4: Migrate Direct Swift Inference Workloads

**Execution model:** `gpt-5.6-terra`, medium reasoning

**Files:**
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceDispatchService.swift`
- Modify: `desktop/macos/Desktop/Sources/AppleNotesReaderService.swift`
- Modify: `desktop/macos/Desktop/Sources/CalendarReaderService.swift`
- Modify: `desktop/macos/Desktop/Sources/GmailReaderService.swift`
- Modify: `desktop/macos/Desktop/Sources/Onboarding/OnboardingMemoryLogImportService.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/PTTContextVocabularyProvider.swift`
- Modify: `desktop/macos/Desktop/Sources/MainWindow/Pages/ChatLabView.swift`
- Modify: `desktop/macos/Desktop/Sources/ProactiveAssistants/Core/GeminiClient.swift`
- Modify: `desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/Insight/InsightAssistant.swift`
- Modify: `desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/Suggestions/SuggestionAssistant.swift`
- Modify: `desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/TaskExtraction/TaskAssistant.swift`
- Modify: `desktop/macos/Desktop/Sources/ProactiveAssistants/Services/EmbeddingService.swift`
- Test: extend the closest existing assistant/reader tests and add `desktop/macos/Desktop/Tests/InferenceDispatchServiceTests.swift`.

**Interfaces:**
- Consumes: resolver from Task 3 and custom client from Task 2.
- Produces: `InferenceDispatching.complete` and `InferenceDispatching.stream`; preserves existing managed transports.

- [ ] **Step 1: Write dispatch-path tests**

```swift
func testManagedRouteUsesExistingManagedExecutor() async throws {
  let managed = ManagedInferenceExecutorStub(result: .text("managed"))
  let custom = CustomInferenceExecutorStub(result: .text("custom"))
  let service = InferenceDispatchService(resolver: managedResolver(), managed: managed, custom: custom)
  _ = try await service.complete(workload: .synthesis, request: .fixture)
  XCTAssertEqual(managed.calls, 1)
  XCTAssertEqual(custom.calls, 0)
}

func testCustomRouteUsesDirectClientAndNeverManagedFallback() async throws {
  let managed = ManagedInferenceExecutorStub(result: .text("managed"))
  let custom = CustomInferenceExecutorStub(error: .providerAuthentication)
  let service = InferenceDispatchService(resolver: customResolver(), managed: managed, custom: custom)
  await XCTAssertThrowsErrorAsync(try await service.complete(workload: .insight, request: .fixture))
  XCTAssertEqual(managed.calls, 0)
}
```

- [ ] **Step 2: Run the dispatch test and confirm red failure**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter InferenceDispatchServiceTests
```

Expected: FAIL because `InferenceDispatchService` does not exist.

- [ ] **Step 3: Implement the dispatch service**

```swift
protocol InferenceDispatching: Sendable {
  func complete(workload: InferenceWorkload, request: InferenceRequest) async throws -> InferenceTerminalResult
  func stream(workload: InferenceWorkload, request: InferenceRequest) -> AsyncThrowingStream<InferenceEvent, Error>
}
```

Resolve additional capabilities from actual content parts/tools/schema. For `.omiManaged`, call the injected current transport. For `.custom`, read the exact revision's key and call `OpenAICompatibleInferenceClient`. Record provider-auth failure through `CredentialHealthManager` without invalidating Firebase.

- [ ] **Step 4: Migrate synthesis and context-vocabulary callers**

At each existing prompt assembly seam, replace the hardcoded model argument with an `InferenceRequest` and workload:

```swift
let result = try await InferenceDispatchService.shared.complete(
  workload: .synthesis,
  request: InferenceRequest(messages: promptMessages, responseSchema: schema, maxOutputTokens: 2_048))
```

Preserve current Omi-managed request functions inside `ManagedInferenceExecutor`; do not duplicate their prompt or parsing logic.

- [ ] **Step 5: Migrate proactive Gemini callers**

Keep `GeminiClient` as the managed Gemini executor. Add conversion between its existing content/schema types and provider-neutral `InferenceRequest`. Use `.proactiveVision`, `.taskExtraction`, `.insight`, or `.suggestion` at the call site. A screenshot adds `.imageInput`; a custom text-only Standard route fails before sending.

- [ ] **Step 6: Migrate ChatLab and isolate embeddings**

Route ChatLab query/grade through `.chatLabQuery` and `.chatLabGrade`. Move the excluded constant to:

```swift
extension EmbeddingService {
  static let managedModelName = "gemini-embedding-001"
}
```

Do not expose embeddings in `InferenceWorkload` or custom Settings.

- [ ] **Step 7: Run affected behavioral tests**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'InferenceDispatchServiceTests|SuggestionAssistantTests|TaskAssistantPromptTests|TaskAssistantContextPromptTests|ModelQoSTests|AssistantSettingsVocabularyTests'
python3 scripts/check_desktop_test_quality.py
```

Expected: PASS. Update or replace `ModelQoSTests` only where the production owner moved; cite the checked-in design as the external contract in the eventual PR body.

- [ ] **Step 8: Search for unowned direct-workload calls**

Run:

```bash
rg -n 'ModelQoS\.(Claude\.(synthesis|chatLab)|Gemini\.(proactive|taskExtraction|insight|suggestions))' desktop/macos/Desktop/Sources
```

Expected: no matches.

- [ ] **Step 9: Commit the direct workload migration**

```bash
git add desktop/macos/Desktop/Sources/Inference desktop/macos/Desktop/Sources/AppleNotesReaderService.swift desktop/macos/Desktop/Sources/CalendarReaderService.swift desktop/macos/Desktop/Sources/GmailReaderService.swift desktop/macos/Desktop/Sources/Onboarding/OnboardingMemoryLogImportService.swift desktop/macos/Desktop/Sources/FloatingControlBar/PTTContextVocabularyProvider.swift desktop/macos/Desktop/Sources/MainWindow/Pages/ChatLabView.swift desktop/macos/Desktop/Sources/ProactiveAssistants desktop/macos/Desktop/Tests
git commit -m "feat(desktop): route background inference by workload"
```

---

### Task 5: Persist Inference Routes in Immutable Kernel Execution Profiles

**Execution model:** `gpt-5.6-sol`, medium reasoning

**Files:**
- Modify: `desktop/macos/agent/src/protocol.ts`
- Modify: `desktop/macos/agent/src/runtime/types.ts`
- Modify: `desktop/macos/agent/src/runtime/sqlite-store.ts`
- Modify: `desktop/macos/agent/src/runtime/session-execution-profile.ts`
- Modify: `desktop/macos/agent/src/runtime/kernel-runs.ts`
- Modify: `desktop/macos/agent/src/runtime/kernel-support.ts`
- Modify: `desktop/macos/agent/src/runtime/jsonl-transport.ts`
- Modify: `desktop/macos/agent/src/runtime/contract-schema.ts`
- Modify: `desktop/macos/Desktop/Sources/Chat/AgentControlService.swift`
- Modify: `desktop/macos/Desktop/Sources/Chat/AgentClient.swift`
- Modify: `desktop/macos/agent/contracts/v1/agent-runtime-contract.fixture.json`
- Test: `desktop/macos/agent/tests/custom-inference-route.test.ts`
- Test: `desktop/macos/agent/tests/session-execution-profile.test.ts`
- Test: `desktop/macos/agent/tests/sqlite-store.test.ts`
- Test: `desktop/macos/agent/tests/agent-runtime-contract-fixtures.test.ts`
- Test: `desktop/macos/Desktop/Tests/InferenceAgentRouteTests.swift`

**Interfaces:**
- Consumes: Swift `InferenceRouteRef` from Task 1.
- Produces cross-language `InferenceRouteRef`, added to default preferences, session profiles, run projections, binding identity, configure/resolve/migrate messages, and Swift response decoding. Task 6 adds it to adapter `SessionOpts` when the Pi execution boundary is updated.
- SQLite migration version: 33, named `INFERENCE_ROUTE_PROFILE_MIGRATION_VERSION`.

- [ ] **Step 1: Write kernel profile and inheritance tests**

```typescript
it("pins an inference route and inherits it into delegated children", async () => {
  const route = { kind: "custom", providerId: "11111111-1111-1111-1111-111111111111", revision: 2, modelId: "glm-5.1" } as const;
  const parent = await configureAndResolve({ adapterId: "pi-mono", inferenceRoute: route });
  const child = await kernel.spawnBackgroundAgent({ callerSessionId: parent.sessionId, prompt: "bounded" });
  expect(readProfile(parent.sessionId).inferenceRoute).toEqual(route);
  expect(readProfile(child.sessionId).inferenceRoute).toEqual(route);
});

it("rejects inference route overrides on an existing session", async () => {
  await expect(kernel.sendAgentMessage({ sessionId, inferenceRoute: otherRoute, prompt: "x" }))
    .rejects.toThrow("Existing session execution profile rejects inference route override");
});
```

- [ ] **Step 2: Write SQLite migration tests from version 32**

Create a version-32 fixture with one `pi-mono` profile and one ACP profile. After migration, assert the Pi profile is backfilled to managed `omi` plus its current model, external profiles remain null, all route JSON is valid, and a second open is idempotent.

- [ ] **Step 3: Write Swift protocol round-trip tests**

```swift
func testExecutionProfileProjectionDecodesCustomRoute() throws {
  let projection = try JSONDecoder().decode(AgentExecutionProfileProjection.self, from: customRouteFixture)
  XCTAssertEqual(projection.inferenceRoute?.providerID.uuidString.lowercased(), "11111111-1111-1111-1111-111111111111")
  XCTAssertEqual(projection.inferenceRoute?.revision, 2)
  XCTAssertEqual(projection.inferenceRoute?.modelID, "glm-5.1")
}
```

- [ ] **Step 4: Run focused Node and Swift tests and confirm red failures**

Run:

```bash
cd desktop/macos/agent
npm test -- custom-inference-route.test.ts session-execution-profile.test.ts sqlite-store.test.ts agent-runtime-contract-fixtures.test.ts
cd ..
xcrun swift test --package-path Desktop --filter InferenceAgentRouteTests
```

Expected: FAIL because the route field and migration do not exist.

- [ ] **Step 5: Add the typed wire contract**

```typescript
export type InferenceRouteRef =
  | { kind: "managed"; providerId: "omi"; revision: 0; modelId: string }
  | { kind: "custom"; providerId: string; revision: number; modelId: string };
```

Add `inferenceRoute: InferenceRouteRef | null` to `SessionExecutionProfile`, `DefaultExecutionProfilePreference`, `AgentSession`, `AgentRun`, `AdapterBinding`, and every kernel configure/resolve/migrate/projection message. Validate UUID/provider format, positive custom revision, revision zero only for managed, bounded model ID, and `custom` only with adapter `pi-mono`. Do not change adapter `SessionOpts` in this task; Task 6 owns that execution-boundary change and its adapter tests.

- [ ] **Step 6: Add migration 33 and row codecs**

Add nullable `inference_route_json TEXT CHECK (inference_route_json IS NULL OR json_valid(inference_route_json))` to `sessions`, `runs`, `adapter_bindings`, `session_execution_profiles`, and `default_execution_profile_preferences`. Backfill Pi profiles to canonical managed route JSON using `model_profile`; leave external adapters null. Update every insert/select/update codec and binding cache identity.

- [ ] **Step 7: Enforce immutable profile behavior**

Update configure, surface creation, explicit migration, send, child derivation, retry, and binding creation. Compare canonical route values with a shared `sameInferenceRoute` helper; never compare raw JSON strings assembled by callers. Existing sessions reject route overrides. Only `migrate_session_execution_profile` with `reason: "user_requested"` increments generation and invalidates stale bindings.

- [ ] **Step 8: Update Swift protocol APIs**

Change signatures to:

```swift
func configureDefaultExecutionProfile(
  adapterId: String,
  modelProfile: String?,
  inferenceRoute: InferenceRouteRef?,
  workingDirectory: String
) async throws -> AgentDefaultExecutionProfile

func migrateSessionExecutionProfile(
  sessionID: String,
  expectedGeneration: Int,
  adapterId: String,
  modelProfile: String?,
  inferenceRoute: InferenceRouteRef?,
  workingDirectory: String
) async throws -> AgentExecutionProfileProjection
```

Update fixture/schema exhaustiveness in the same step.

- [ ] **Step 9: Run kernel and contract tests**

Run:

```bash
cd desktop/macos/agent
npm test -- custom-inference-route.test.ts session-execution-profile.test.ts sqlite-store.test.ts agent-runtime-contract-fixtures.test.ts adapter-binding.test.ts
npm run build
cd ..
xcrun swift test --package-path Desktop --filter 'InferenceAgentRouteTests|AgentRuntimeContractFixtureTests'
```

Expected: PASS, including migration idempotency and child inheritance.

- [ ] **Step 10: Commit the kernel contract**

```bash
git add desktop/macos/agent desktop/macos/Desktop/Sources/Chat/AgentControlService.swift desktop/macos/Desktop/Sources/Chat/AgentClient.swift desktop/macos/Desktop/Tests/InferenceAgentRouteTests.swift desktop/macos/Desktop/Tests/fixtures/agent-runtime-contract
git commit -m "feat(agent): persist inference routes in session profiles"
```

---

### Task 6: Dynamically Register Custom Providers in the Bundled Pi Runtime

**Execution model:** `gpt-5.6-sol`, medium reasoning

**Files:**
- Modify: `desktop/macos/Desktop/Sources/Chat/AgentRuntimeProcess.swift`
- Modify: `desktop/macos/Desktop/Sources/Chat/AgentRuntimePayload.swift`
- Modify: `desktop/macos/Desktop/Tests/AgentRuntimeProcessTests.swift`
- Modify: `desktop/macos/agent/src/adapters/interface.ts`
- Modify: `desktop/macos/agent/src/adapters/pi-mono.ts`
- Modify: `desktop/macos/pi-mono-extension/index.ts`
- Test: `desktop/macos/agent/tests/custom-inference-provider.test.ts`
- Test: `desktop/macos/pi-mono-extension/custom-provider.test.ts`

**Interfaces:**
- Consumes: immutable route from Task 5 and configuration/credential stores from Task 1.
- Produces: `OMI_CUSTOM_INFERENCE_ROUTES_JSON` non-secret manifest, indexed `OMI_CUSTOM_INFERENCE_KEY_<N>` secret env names, dynamic Pi registrations, and provider-aware `set_model`.

- [ ] **Step 1: Write Swift environment-export tests**

```swift
@MainActor
func testRuntimeManifestSeparatesMetadataFromSecrets() throws {
  let export = try AgentRuntimeProcess.customInferenceEnvironment(configurations: [.zaiFixture], credentials: credentials)
  let manifest = try XCTUnwrap(export.values["OMI_CUSTOM_INFERENCE_ROUTES_JSON"])
  XCTAssertTrue(manifest.contains("glm-5.1"))
  XCTAssertFalse(manifest.contains("secret-zai"))
  XCTAssertEqual(export.values["OMI_CUSTOM_INFERENCE_KEY_0"], "secret-zai")
}

func testInheritedCustomInferenceEnvironmentIsRemoved() {
  var env = ["OMI_CUSTOM_INFERENCE_KEY_99": "host-secret", "PATH": "/bin"]
  AgentRuntimeProcess.removeInheritedCustomInferenceEnvironment(from: &env)
  XCTAssertNil(env["OMI_CUSTOM_INFERENCE_KEY_99"])
}
```

- [ ] **Step 2: Write Pi extension registration tests**

```typescript
test("registers managed and custom providers without exposing keys", () => {
  const pi = fakePi();
  loadExtension(pi, customManifestFixture, { OMI_CUSTOM_INFERENCE_KEY_0: "secret" });
  expect(pi.providers.map((p) => p.id)).toEqual(["omi", "custom-11111111-r2"]);
  expect(pi.providers[1].config.models[0].id).toBe("glm-5.1");
  expect(capturedStderr).not.toContain("secret");
});
```

- [ ] **Step 3: Write adapter provider/model selection tests**

```typescript
it("selects the provider pinned in the session route", async () => {
  await adapter.createSession({ cwd: "/tmp/project", model: "glm-5.1", inferenceRoute: customRoute });
  expect(lastCommand()).toEqual({ type: "set_model", provider: "custom-11111111-r2", modelId: "glm-5.1" });
});

it("keeps managed Omi selection for a managed route", async () => {
  await adapter.createSession({ cwd: "/tmp/project", model: "omi-sonnet", inferenceRoute: managedRoute });
  expect(lastCommand()).toEqual({ type: "set_model", provider: "omi", modelId: "omi-sonnet" });
});
```

- [ ] **Step 4: Run the new tests and confirm red failures**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter AgentRuntimeProcessTests
cd agent
npm test -- custom-inference-provider.test.ts pi-mono-adapter.test.ts
cd ../pi-mono-extension
npx --yes tsx --test custom-provider.test.ts
```

Expected: FAIL because the manifest, secret export, and dynamic registration do not exist.

- [ ] **Step 5: Implement bounded runtime export**

Export at most 32 retained revisions, sorted by revision ID for deterministic indices. The JSON entry is:

```json
{
  "runtimeProviderId": "custom-11111111-r2",
  "providerId": "11111111-1111-1111-1111-111111111111",
  "revision": 2,
  "preset": "zai",
  "baseUrl": "https://api.z.ai/api/paas/v4",
  "modelId": "glm-5.1",
  "contextWindow": 200000,
  "maxOutputTokens": 16384,
  "capabilities": ["text", "streaming", "tools", "reasoning"],
  "keyEnvironmentName": "OMI_CUSTOM_INFERENCE_KEY_0"
}
```

Remove all inherited `OMI_CUSTOM_INFERENCE_*` variables before adding store-owned values. Refuse startup if a manifest entry lacks its key. Never print manifest values beyond count/preset/model-safe identifiers.

- [ ] **Step 6: Dynamically register providers in the Pi extension**

Parse with strict bounds before registration. Map preset capabilities into Pi's provider model descriptor and register each stable `runtimeProviderId` with `api: "openai-completions"`, normalized base URL, bearer key, and one exact model. Keep the managed `omi` registration unchanged. Add preset-specific request hooks only through shared normalization helpers; do not fork the Omi tools or denylist.

- [ ] **Step 7: Make Pi session selection provider-aware**

Extend `SessionOpts` and warmup cache identity with `inferenceRoute`. Remove the unconditional `provider: "omi"` selection. Managed routes map Claude legacy aliases only at the managed boundary; custom model IDs pass through exactly. Include provider ID/revision/model in binding identity so two providers with the same model name cannot reuse a session.

- [ ] **Step 8: Run agent, extension, payload, and redaction tests**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'AgentRuntimeProcessTests|AgentRuntimePayloadTests'
cd agent
npm test -- custom-inference-provider.test.ts pi-mono-adapter.test.ts runtime-adapter.test.ts
npm run build
cd ../pi-mono-extension
npx --yes tsx --test index.test.ts custom-provider.test.ts
```

Expected: PASS; test output and captured stderr contain no fixture secret.

- [ ] **Step 9: Commit dynamic provider execution**

```bash
git add desktop/macos/Desktop/Sources/Chat/AgentRuntimeProcess.swift desktop/macos/Desktop/Sources/Chat/AgentRuntimePayload.swift desktop/macos/Desktop/Tests/AgentRuntimeProcessTests.swift desktop/macos/agent desktop/macos/pi-mono-extension
git commit -m "feat(agent): run sessions on custom inference providers"
```

---

### Task 7: Wire Main, Floating, Task, Onboarding, and Delegated Agent Surfaces

**Execution model:** `gpt-5.6-sol`, medium reasoning

**Files:**
- Modify: `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- Modify: `desktop/macos/Desktop/Sources/Chat/AgentClient.swift`
- Modify: `desktop/macos/Desktop/Sources/Onboarding/OnboardingChatView.swift`
- Modify: `desktop/macos/Desktop/Sources/Onboarding/OnboardingPagedIntroCoordinator.swift`
- Modify: `desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/TaskAgent/TaskChatRuntime.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubController+Tools.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/RealtimeHubTools.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/ShortcutSettings.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingControlBarState.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingControlBarView.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingControlBarWindow.swift`
- Modify: `desktop/macos/Desktop/Sources/FloatingControlBar/AgentPill.swift`
- Modify: `desktop/macos/Desktop/Sources/MemoryExportExecutor.swift`
- Delete: `desktop/macos/Desktop/Sources/ModelQoS.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceAgentRouteTests.swift`
- Modify affected chat, task-agent, shortcut, floating-bar, continuity, and runtime tests.

**Interfaces:**
- Consumes: resolver, kernel route field, and dynamic Pi registration from Tasks 3, 5, and 6.
- Produces: route-pinned Omi AI sessions and explicit user-requested migration; removes all text callers of `ModelQoS`.

- [ ] **Step 1: Write cross-surface route-pinning tests**

```swift
@MainActor
func testOmiAISurfacesResolveExpectedWorkloadsAndSameReasoningRoute() async throws {
  let resolver = RecordingInferenceResolver(customReasoningRoute)
  let provider = makeChatProvider(resolver: resolver)
  _ = try await provider.resolveAgentSurfaceSession(.mainChat(chatId: nil))
  _ = try await provider.resolveAgentSurfaceSession(.floatingChat())
  XCTAssertEqual(resolver.workloads, [.mainChat, .floatingChat])
  XCTAssertEqual(provider.capturedProfiles.map(\.inferenceRoute), [customReasoningRoute, customReasoningRoute])
}

func testExternalRuntimeRejectsCustomInferenceRoute() async throws {
  let provider = makeChatProvider(mode: .userClaude, route: customReasoningRoute)
  await XCTAssertThrowsErrorAsync(try await provider.configureDefaultProfile())
}
```

- [ ] **Step 2: Write explicit migration and in-flight generation tests**

Assert changing a level does not mutate an existing session, “Apply to current Omi AI chats” calls `migrateSessionExecutionProfile` with the expected generation, stale generations are rejected, and an in-flight run completes on its original route.

- [ ] **Step 3: Run focused route tests and confirm red failures**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'InferenceAgentRouteTests|RuntimeOwnerIdentityTests|ChatTimelineContinuityTests'
```

Expected: FAIL because chat surfaces do not resolve or persist custom inference routes.

- [ ] **Step 4: Resolve routes at session creation boundaries**

Main, floating, task, onboarding, delegated, higher-model, and memory-export agent entry points each request their exact `InferenceWorkload`. Pass the resulting route in default/creation/migration profile calls. For external adapters, pass `nil` and reject a custom assignment before starting the runtime.

Do not select a route in individual send calls. A send uses the immutable session profile already resolved by the kernel.

- [ ] **Step 5: Replace shortcut and floating model strings**

Remove `shortcut_selectedModel`, `availableModels`, and sanitized Claude model selection. Shortcut/floating surfaces show the effective Reasoning & Agents connection label and use `.floatingChat`; the central Settings assignment owns changes. Add a one-time migration that discards the obsolete persisted model string after preserving managed behavior.

- [ ] **Step 6: Route higher-model and delegated work explicitly**

Replace hardcoded Sonnet/Haiku strings in `RealtimeHubTools`, `RealtimeHubController+Tools`, and `AgentPill` with `.higherModel` or `.delegatedAgent`. Child derivation must inherit the parent route unless the human explicitly launches through a separately configured workload override before session creation.

- [ ] **Step 7: Delete `ModelQoS` and install the final source tripwire**

Move the embedding managed default as specified in Task 4, delete `ModelQoS.swift`, and update/remove `ModelQoSTests.swift` so behavior is covered by `InferenceRouteResolverTests` and consumer tests.

Extend `InferenceWorkloadCompletenessTests` with the narrow static assertion that production text-inference callers contain no `ModelQoS` reference. Mark that assertion:

```swift
// omi-test-quality: source-inspection -- static contract: every text inference call site must name the central workload routing authority
```

Keep this as a forbidden-pattern tripwire only; the workload and consumer behavioral tests prove actual resolution.

Run:

```bash
rg -n 'ModelQoS\.' desktop/macos/Desktop/Sources desktop/macos/Desktop/Tests
rg -n 'claude-(sonnet|haiku|opus)' desktop/macos/Desktop/Sources/Providers desktop/macos/Desktop/Sources/Chat desktop/macos/Desktop/Sources/FloatingControlBar desktop/macos/Desktop/Sources/Onboarding desktop/macos/Desktop/Sources/ProactiveAssistants
```

Expected: no `ModelQoS` matches. Any remaining provider model literal must be an explicitly documented managed-default or fixture, not a runtime selection path.

- [ ] **Step 8: Run cross-surface and agent logic tests**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'InferenceAgentRouteTests|RuntimeOwnerIdentityTests|ChatTimelineContinuityTests|FloatingControlBarStateTests|TaskChatLegacyAcpMigrationTests'
./scripts/agent-logic-harness.sh --cross-surface-smoke
python3 scripts/check_desktop_test_quality.py
```

Expected: PASS; Main/floating continuity stays one timeline and route changes do not create a second provider or transcript owner.

- [ ] **Step 9: Commit surface wiring and hardcoded-model removal**

```bash
git add desktop/macos/Desktop/Sources desktop/macos/Desktop/Tests
git commit -m "feat(desktop): apply custom inference across Omi AI"
```

---

### Task 8: Settings, Connection Probes, and Automation Coverage

**Execution model:** `gpt-5.6-terra`, medium reasoning

**Files:**
- Create: `desktop/macos/Desktop/Sources/Inference/InferenceConnectionProbe.swift`
- Create: `desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+Inference.swift`
- Modify: `desktop/macos/Desktop/Sources/MainWindow/Pages/SettingsPage.swift`
- Modify: `desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+Advanced.swift`
- Modify: `desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Sections/SettingsContentView+FloatingBarAndChat.swift`
- Modify: `desktop/macos/Desktop/Sources/DesktopAutomationBridge.swift`
- Modify: `desktop/macos/Desktop/Tests/DesktopAutomationSecondaryActionTests.swift`
- Test: `desktop/macos/Desktop/Tests/InferenceSettingsTests.swift`
- Create: `desktop/macos/e2e/fixtures/fake_openai_compatible_provider.py`
- Modify: `desktop/macos/e2e/flows/ai-chat-settings.yaml`

**Interfaces:**
- Consumes: store, resolver, and client from Tasks 1–3.
- Produces: Settings workflows, capability probes, `inference_settings_snapshot`, `inference_connection_upsert`, `inference_connection_test`, and `inference_level_assign` non-production automation actions.

- [ ] **Step 1: Write probe tests against an injected fake executor**

```swift
func testReasoningAgentProbeRequiresTextStreamingAndTools() async throws {
  let probe = InferenceConnectionProbe(executor: ProbeExecutorStub(supported: [.text, .streaming, .tools]))
  let result = try await probe.test(.fixture, for: .reasoningAgent)
  XCTAssertEqual(result.provenCapabilities, [.text, .streaming, .tools])
}

func testFailedToolProbePreventsAssignment() async throws {
  let probe = InferenceConnectionProbe(executor: ProbeExecutorStub(supported: [.text, .streaming]))
  await XCTAssertThrowsErrorAsync(try await probe.test(.fixture, for: .reasoningAgent))
}
```

- [ ] **Step 2: Write Settings behavior tests**

Test preset defaults remain editable, Save requires a basic text probe, assignment requires target-level capabilities, key text is never present in a snapshot, disabled revisions disappear from new assignment menus, referenced revisions cannot be deleted, and the privacy/free-plan disclosures render.

- [ ] **Step 3: Run UI/probe tests and confirm red failures**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'InferenceSettingsTests|DesktopAutomationSecondaryActionTests'
```

Expected: FAIL because the UI, probe, and actions do not exist.

- [ ] **Step 4: Implement capability probes**

The basic probe sends a non-streaming one-token text request. Level probes add:

- Fast: structured-output probe only if a selected Fast workload needs it.
- Standard: structured output plus a 1×1 local image when the assignment covers `.proactiveVision`.
- Reasoning & Agents: streaming and a deterministic local `return_token` function call.

Never persist prompts or raw responses. Return bounded per-capability results. A provider/model response that declines the deterministic tool is a failed tool capability test, not success.

- [ ] **Step 5: Build the Inference Settings section**

Add three level cards, Connections list, editor sheet, test state, Advanced Workload Overrides, direct-provider disclosure, and free-plan boundary note. Presets fill:

```swift
static let defaults: [InferenceCompatibilityPreset: URL] = [
  .zai: URL(string: "https://api.z.ai/api/paas/v4")!,
  .kimi: URL(string: "https://api.moonshot.ai/v1")!,
  .deepSeek: URL(string: "https://api.deepseek.com")!,
]
```

Generic requires manual base URL. Every model ID remains editable/manual. Rename the existing “AI Provider” label to “Agent Runtime.” Use existing Settings glass components and neutral/white accents only.

- [ ] **Step 6: Add the permanent hermetic provider fixture**

Create `e2e/fixtures/fake_openai_compatible_provider.py` using only Python's standard library and start it on an explicitly supplied loopback port. Give it a `# LIFECYCLE: permanent` header. It must implement bounded `/v1/chat/completions` non-streaming and SSE responses, fragmented tool arguments, deterministic structured output, auth failure, malformed stream, delayed stream for cancellation, and a sanitized request-metadata endpoint. It must never retain or return the Authorization header or prompt bodies. Add a `--self-check` mode that starts the fixture on an ephemeral port, exercises every response mode, verifies the redaction contract, and exits.

Wire the fixture into `ai-chat-settings.yaml` and the existing desktop E2E runner so its self-check runs in the same existing CI lane as the flow; do not create a new on-demand-only validation script.

- [ ] **Step 7: Add safe automation actions and e2e assertions**

`inference_settings_snapshot` returns IDs/presets/hosts/models/capabilities/assignments and Keychain state (`present`, `missing`, `unavailable`) but never keys or base-URL paths. Mutating actions are non-production only and accept a key through the local automation request without echoing it in results/logs.

Update `ai-chat-settings.yaml` to navigate to Advanced, create a loopback Generic connection against the hermetic fake, test it, assign Reasoning & Agents, assert the snapshot, and delete it. Do not add live internet or provider credentials to CI.

- [ ] **Step 8: Run UI, automation, layout, fixture, and formatting checks**

Run:

```bash
cd desktop/macos
./scripts/swift-format-wrapper.sh format -i Desktop/Sources/Inference Desktop/Sources/MainWindow/Pages/Settings Desktop/Sources/DesktopAutomationBridge.swift Desktop/Tests/InferenceSettingsTests.swift
xcrun swift test --package-path Desktop --filter 'InferenceSettingsTests|DesktopAutomationSecondaryActionTests|SettingsControlMetricsTests|SettingsGlassChromeTests'
python3 e2e/fixtures/fake_openai_compatible_provider.py --self-check
./scripts/swift-format-wrapper.sh lint -r $(./scripts/swift-format-wrapper.sh scope)
```

Expected: PASS with no purple-token or Settings layout regression.

- [ ] **Step 9: Commit Settings and automation**

```bash
git add desktop/macos/Desktop/Sources/Inference/InferenceConnectionProbe.swift desktop/macos/Desktop/Sources/MainWindow/Pages/Settings desktop/macos/Desktop/Sources/DesktopAutomationBridge.swift desktop/macos/Desktop/Tests desktop/macos/e2e/fixtures/fake_openai_compatible_provider.py desktop/macos/e2e/flows/ai-chat-settings.yaml
git commit -m "feat(desktop): configure inference providers in Settings"
```

---

### Task 9: Documentation, Real-Path Verification, and PR Contracts

**Execution model:** `gpt-5.6-terra`, medium reasoning

**Final independent review:** `gpt-5.6-sol`, high reasoning, review-only unless findings require the owning task worker to fix them.

**Files:**
- Modify: `desktop/macos/AGENTS.md`
- Modify: `docs/doc/developer/agent-control-plane.mdx`
- Create: `docs/doc/developer/desktop/custom-inference-providers.mdx`
- Create: `desktop/macos/changelog/unreleased/20260808-custom-inference-providers.json`
- Create/update: exact PR body file outside the repository, `/tmp/omi-custom-inference-pr-body.md`.

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: durable ownership/verification guidance, named-bundle evidence, live compatibility evidence, preflight evidence, and final independent review.

- [ ] **Step 1: Update durable documentation**

Document:

- Agent Runtime vs inference-provider ownership.
- Fast/Standard/Reasoning & Agents workload mapping and workload overrides.
- Keychain-at-rest and direct-provider data disclosure.
- HTTPS/loopback endpoint policy and no silent fallback.
- Generic, Z.AI, Kimi, and DeepSeek preset behavior.
- Existing-session pinning and explicit migration.
- Free-plan/BYOK and excluded modality boundaries.
- Focused tests, fake endpoint, named-bundle, prompt gauntlet, and credentialed live smoke.

Add the changelog fragment:

```json
{
  "change": "Added custom inference providers and per-workload model routing on Mac"
}
```

- [ ] **Step 2: Run all focused hermetic suites**

Run:

```bash
cd desktop/macos
xcrun swift test --package-path Desktop --filter 'Inference'
python3 scripts/check_desktop_test_quality.py
./scripts/agent-logic-harness.sh --cross-surface-smoke
cd agent
npm test
npm run build
cd ../pi-mono-extension
npx --yes tsx --test index.test.ts custom-provider.test.ts
```

Expected: all tests and builds PASS.

- [ ] **Step 3: Build and launch the named bundle**

Run:

```bash
cd desktop/macos
OMI_APP_NAME=omi-custom-inference OMI_SKIP_TUNNEL=1 ./run.sh
# In a second shell, derive the same per-worktree automation port used by run.sh.
source ../../scripts/dev-instance.sh
OMI_AUTOMATION_PORT="$AUTOMATION_PORT" ./scripts/omi-ctl health
OMI_AUTOMATION_PORT="$AUTOMATION_PORT" ./scripts/omi-ctl navigate settings advanced --show
```

Expected: the named bundle is healthy, signed as a non-production bundle, and Advanced Settings shows Inference without touching Omi/Omi Beta.

- [ ] **Step 4: Exercise the real custom route through the local fake endpoint**

Through semantic automation actions or `agent-swift`, create and test the loopback provider, assign all three levels, then exercise:

1. Fast structured suggestion/grade fixture.
2. Standard structured synthesis fixture.
3. Main Chat streaming text and a tool call.
4. Floating Chat on the same continuity timeline.
5. Delegated child agent inheriting the route.
6. Cancellation.
7. Invalid key and capability mismatch.
8. Explicit migration of an existing session.

Capture `inference_settings_snapshot`, chat snapshots, kernel session projection, bounded app logs, and fake-server request metadata. Assert no key appears in any capture.

- [ ] **Step 5: Run one credentialed named-provider smoke**

Using a credential supplied outside the repo and shell history, configure one of Z.AI, Kimi, or DeepSeek in the named bundle. Run one streaming text turn and one deterministic tool turn. Record only provider preset, host, model ID, status, and sanitized timing. Remove the test connection and Keychain revision afterward through the app UI.

If no live credential is available, mark this step `NOT RUN` in the PR body and do not claim named-provider live verification; the local fake still proves the app flow but not provider compatibility.

- [ ] **Step 6: Run prompt compatibility and desktop doctor gates**

Run:

```bash
cd desktop/macos
./scripts/agent-continuity-gauntlet.sh --suite prompts --bundle-id com.omi.omi-custom-inference
./scripts/check-gauntlet-evidence-at-head.sh
./scripts/omi-macos-dev doctor
```

Expected: prompt suite PASS with a public-web source URL on the custom tool-compatible route, evidence matches HEAD, and doctor reports no blocking issue.

- [ ] **Step 7: Run component and PR contracts**

Run:

```bash
cd desktop/macos
./test.sh
cd ../..
scripts/pr-preflight --suggest
make preflight
scripts/pr-preflight --pr-body-file /tmp/omi-custom-inference-pr-body.md
git diff --check origin/main...HEAD
```

Expected: desktop component suite, manifest checks, preflight, PR-body contract, and diff check PASS. Put every matched invariant ID and the exact test/live evidence in the PR body. Declare the failure class required by `scripts/pr-preflight --suggest`.

- [ ] **Step 8: Run the independent `gpt-5.6-sol` high review**

Review only these high-risk questions:

- Can a key enter persistence, protocol, logs, telemetry, fixtures, crash reports, or automation output?
- Can URL or redirect handling reach a forbidden target?
- Can a custom failure silently cross to managed inference or invalidate Firebase auth?
- Can route edits mutate an in-flight/pinned session or break child inheritance?
- Can equal model IDs across providers reuse a binding?
- Does every text inference call site name a workload, with excluded modalities still excluded?
- Does Main/floating/task/onboarding continuity retain one authoritative timeline?
- Do Z.AI/Kimi/DeepSeek fixtures cover their documented wire differences?

Return findings with file/line evidence. Send each valid finding back to the task that owns it, rerun that task's focused checks, then rerun Steps 2, 6, and 7.

- [ ] **Step 9: Commit documentation and final verified fixes**

```bash
git add desktop/macos/AGENTS.md docs/doc/developer/agent-control-plane.mdx docs/doc/developer/desktop/custom-inference-providers.mdx desktop/macos/changelog/unreleased/20260808-custom-inference-providers.json
git commit -m "docs(desktop): document custom inference routing"
```

- [ ] **Step 10: Stop before push or PR**

Do not push, open a PR, merge, deploy, or touch `main` without current explicit user authorization. Report the local branch, commits, verification evidence, live-provider status, and any residual risk.

---

## Plan Self-Review Checklist

- [ ] Every design requirement maps to a task: configuration and Keychain (1), provider compatibility (2), levels/workloads (3), direct workloads (4), immutable profiles (5), Pi execution (6), all agent surfaces (7), UI/probes (8), and verification/docs (9).
- [ ] Every custom-route failure path is fail-closed and preserves Firebase auth.
- [ ] No task adds a backend arbitrary-endpoint route or forwards a custom key to Omi.
- [ ] No task treats embeddings, STT, realtime voice, TTS, or image generation as an OpenAI Chat Completions workload.
- [ ] Type names are consistent: `InferenceProviderRevisionID`, `InferenceRouteSelection`, `InferenceRouteRef`, `ResolvedInferenceRoute`, `InferenceWorkload`, and `InferenceCapability`.
- [ ] The only `gpt-5.6-sol` high assignment is the final independent security/cross-surface review.
