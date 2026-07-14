# PTT hub shadow-state census (Phase 1b)

Floor list plus adjacent turn/run/spawn/journal facts on `RealtimeHubController`.

| Property | Bucket | Owner / action |
|---|---|---|
| `prefetchedVoiceContext*` / `sessionVoiceContextFreshnessIdentity` | (a) pure cache | Rebuild via `fetchVoiceContextSnapshot` / `refreshVoiceContextSnapshot` |
| `turnPersistenceLedger` obligations (`Task`) | (b) genuinely local | In-flight write handles; die with process |
| `turnPersistenceLedger` receipts | (c) shadow truth | Rebuild via `RealtimeHubContinuityRestore.kernelOwnsExchange` — never disk |
| `acceptedSpawnJournalReceiptByContinuityKey` | (c) shadow truth | Kernel journal / voice-context turn IDs are authoritative; hub map is write-through for this process |
| `completedAuthorizedRealtimeInvocationIDs` | (b) genuinely local | In-session delivery dedupe; kernel authorizes each run |
| `authorizedRealtimeInvocations` | (b) genuinely local | In-flight envelopes |
| `externalRunAuthorityState` / `externalRunTerminalizations` | (b) genuinely local | In-flight `Task` handles |
| `toolEffectIdentityByTransportKey` | (b) genuinely local | Transport↔reducer correlation |
| `cancelContinuityFence*` / `ownerBoundaryGeneration` | (b) genuinely local | Race fences |
| `reconnectAudioBuffer` / `replacementAudioBuffer` | (b) genuinely local | Buffered PCM for this process |
| `geminiSessionNeedsTurnBoundary` | (b) genuinely local | Provider-specific fence |

Proven (c) seam: `RealtimeHubContinuityRestore.kernelOwnsExchange` + `RealtimeTurnJournalAuthority.persist(kernelOwnsExchange:)` — reuses `KernelTurnProjection.stableTurnIDs`, no omnibus protocol, no ledger disk persistence.
