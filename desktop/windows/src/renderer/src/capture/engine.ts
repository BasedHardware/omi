// The single seam between Agent A's capture hosts and the audio engine. For now
// it re-exports Agent A's thin shim (./enginesShim). At integration the
// orchestrator flips this ONE file to re-export Agent B's real engine:
//
//   export * from '../lib/capture/pcmPipeline'
//   export * from '../lib/capture/vadGate'
//
// B publishes the same signatures (createPcmPipeline / createVadGate and the
// PcmPipeline / VadGate / VadGateConfig / VadMode types), so no host changes.
export * from './enginesShim'
