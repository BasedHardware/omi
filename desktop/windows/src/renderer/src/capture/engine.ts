// The single seam between the capture hosts and the audio engine. It re-exports
// Agent B's real engine (src/renderer/src/lib/capture/captureEngine), which
// publishes the exact contract the hosts call — createPcmPipeline / createVadGate
// and the PcmPipeline / VadGate / VadGateConfig / VadMode types — so the hosts need
// no changes. (The earlier ./enginesShim passthrough placeholder is retired.)
export * from '../lib/capture/captureEngine'
