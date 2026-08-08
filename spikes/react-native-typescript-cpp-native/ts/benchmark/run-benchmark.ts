/**
 * Spike Benchmark: Adapter/Controller Overhead Comparison
 *
 * Measures LOCAL adapter/controller overhead only using Node perf_hooks.
 * This is NOT a UI, browser, or ASR performance benchmark.
 *
 * Compares:
 *   (A) Current TypeScript controller/adapter shape
 *   (B) React Native native-module bridge path (simulated)
 *   (C) Web TypeScript adapter (crepuscularity.tsc.hk + Moonshine boundary model)
 *
 * Run:
 *   node --experimental-strip-types ts/benchmark/run-benchmark.ts
 *
 * All inputs are deterministic synthetic packets. No network dependencies.
 */

import { performance } from 'node:perf_hooks';

import {
  CurrentTsAdapter,
  ReactNativeNativeModuleAdapter,
  WebTypescriptAdapter,
  buildSyntheticPacket,
} from './adapters.ts';

// ─── Configuration ───────────────────────────────────────────────────────────

const ITERATIONS = 10_000;
const WARMUP_ITERATIONS = 1_000;
const PAYLOAD_SIZES = [16, 64, 256, 1024];

// ─── Benchmark harness ──────────────────────────────────────────────────────

interface BenchmarkResult {
  adapter: string;
  payloadBytes: number;
  iterations: number;
  totalMs: number;
  avgUs: number;
  opsPerSec: number;
  checksumSample: number;
  normalizeSuccessCount: number;
}

function runSingleBenchmark(
  name: string,
  adapter: { calculateChecksum(d: Uint8Array): number; normalizePacket(d: Uint8Array): { status: string } },
  packet: Uint8Array,
  payloadSize: number,
): BenchmarkResult {
  let checksumSample = 0;
  let normalizeSuccessCount = 0;

  // Warmup (not measured)
  for (let i = 0; i < WARMUP_ITERATIONS; i++) {
    adapter.calculateChecksum(packet.subarray(2, 2 + payloadSize));
    adapter.normalizePacket(packet);
  }

  // Measured run
  const start = performance.now();
  for (let i = 0; i < ITERATIONS; i++) {
    checksumSample = adapter.calculateChecksum(packet.subarray(2, 2 + payloadSize));
    const result = adapter.normalizePacket(packet);
    if (result.status === 'SUCCESS') normalizeSuccessCount++;
  }
  const end = performance.now();

  const totalMs = end - start;
  const avgUs = (totalMs / ITERATIONS) * 1000;
  const opsPerSec = Math.round((ITERATIONS / totalMs) * 1000);

  return {
    adapter: name,
    payloadBytes: payloadSize,
    iterations: ITERATIONS,
    totalMs: Math.round(totalMs * 100) / 100,
    avgUs: Math.round(avgUs * 100) / 100,
    opsPerSec,
    checksumSample,
    normalizeSuccessCount,
  };
}

// ─── Main ────────────────────────────────────────────────────────────────────

console.log('╔══════════════════════════════════════════════════════════════════╗');
console.log('║  Spike Benchmark: Adapter/Controller Overhead Comparison       ║');
console.log('║  ⚠  LOCAL OVERHEAD ONLY — NOT UI/BROWSER/ASR PERFORMANCE      ║');
console.log('╚══════════════════════════════════════════════════════════════════╝');
console.log('');
console.log(`Iterations: ${ITERATIONS.toLocaleString()} (warmup: ${WARMUP_ITERATIONS.toLocaleString()})`);
console.log(`Payload sizes: ${PAYLOAD_SIZES.join(', ')} bytes`);
console.log(`Node: ${process.version}`);
console.log(`Platform: ${process.platform} ${process.arch}`);
console.log(`Date: ${new Date().toISOString()}`);
console.log('');

const adapters = [
  { name: '(A) Current TS Adapter', instance: new CurrentTsAdapter() },
  { name: '(B) RN Native-Module Bridge', instance: new ReactNativeNativeModuleAdapter() },
  { name: '(C) Web TS Adapter (Moonshine)', instance: new WebTypescriptAdapter() },
] as const;

const allResults: BenchmarkResult[] = [];

for (const payloadSize of PAYLOAD_SIZES) {
  console.log(`─── Payload: ${payloadSize} bytes ───`);
  const packet = buildSyntheticPacket(payloadSize);

  for (const { name, instance } of adapters) {
    // Reset web adapter render cache between payload sizes for fair measurement
    if ('resetRenderCache' in instance) {
      (instance as WebTypescriptAdapter).resetRenderCache();
    }

    const result = runSingleBenchmark(name, instance, packet, payloadSize);
    allResults.push(result);

    const statusLabel = result.normalizeSuccessCount === ITERATIONS ? '✓ all' : `${result.normalizeSuccessCount}/${ITERATIONS}`;
    console.log(
      `  ${result.adapter.padEnd(35)} ${result.totalMs.toString().padStart(8)} ms` +
      `  │ ${result.avgUs.toString().padStart(8)} µs/op` +
      `  │ ${result.opsPerSec.toLocaleString().padStart(12)} ops/s` +
      `  │ normalize: ${statusLabel}`
    );
  }
  console.log('');
}

// ─── Summary matrix ──────────────────────────────────────────────────────────

console.log('═══ BENCHMARK MATRIX (µs/op — lower is better) ═══');
console.log('');

const header = ['Adapter', ...PAYLOAD_SIZES.map(s => `${s}B`)].map((h, i) =>
  i === 0 ? h.padEnd(35) : h.padStart(10)
).join(' │ ');
console.log(header);
console.log('─'.repeat(header.length));

for (const { name } of adapters) {
  const row = [
    name.padEnd(35),
    ...PAYLOAD_SIZES.map(size => {
      const r = allResults.find(r => r.adapter === name && r.payloadBytes === size);
      return r ? `${r.avgUs} µs`.padStart(10) : 'N/A'.padStart(10);
    }),
  ].join(' │ ');
  console.log(row);
}

console.log('');
console.log('─── Moonshine Integration Boundary ───');
console.log('Moonshine (https://crepuscularity.tsc.hk) is documented as an');
console.log('EXTERNAL speech/voice integration boundary. It is NOT a dependency');
console.log('of this benchmark. The Web TS Adapter (C) models the boundary');
console.log('contract shape and measures stub dispatch overhead only.');
console.log('');
console.log('─── Browser Verification ───');
console.log('To verify the crepuscularity.tsc.hk site in a browser:');
console.log('  1. Open: https://crepuscularity.tsc.hk');
console.log('  2. Observe the live WASM-rendered landing page');
console.log('  3. Footer shows: "ISC — built with crepuscularity + moonshine"');
console.log('  curl -sI https://crepuscularity.tsc.hk | head -5');
console.log('');
console.log('NOTE: The external URL was reachable via HTTP at benchmark authoring');
console.log('time. If blocked in your environment, this does not affect local');
console.log('benchmark results. The benchmark has zero network dependencies.');
console.log('');
console.log('─── Proof Limits ───');
console.log('• Measures adapter/controller overhead ONLY (not UI, browser, or ASR)');
console.log('• Synthetic deterministic inputs — not real device packets');
console.log('• Simulated JSI/TurboModule bridge — not actual native module calls');
console.log('• Moonshine boundary is a typed stub — not real speech processing');
console.log('• Node.js perf_hooks timing — not React Native runtime timing');
