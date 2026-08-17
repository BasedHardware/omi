import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function hasSwiftc() {
  try { execFileSync("swiftc", ["--version"], { stdio: "ignore" }); return true; }
  catch { return false; }
}

const HARNESS = String.raw`
import Foundation
import AVFoundation

let base = URL(string: "https://staging.example.test/api")!
let authority = ShellTransportAuthority(baseURL: base, token: "shell-token")
let audio = deterministicListenEvidenceAudio()
print("AUDIO-BYTES=\(audio.count)")
for sample in [0, 1, 1599] {
  let bits = UInt16(audio[sample * 2]) | (UInt16(audio[sample * 2 + 1]) << 8)
  print("SAMPLE-\(sample)=\(Int16(bitPattern: bits))")
}
print("READY=\(isListenProtocolReady("{\"type\":\"service_status\",\"status\":\"ready\"}"))")
print("NOT-READY=\(isListenProtocolReady("{\"type\":\"service_status\",\"status\":\"starting\"}"))")
let decision = authority.prepareListen(
  id: "listen-1", path: "/v4/listen?language=en", clientId: "run-listen-proof")
if case let .dispatch(prepared) = decision {
  let notDetermined = ListenPreflightPolicy.payload(permission: .notDetermined, inputAvailable: true)
  let denied = ListenPreflightPolicy.payload(permission: .denied, inputAvailable: true)
  let granted = ListenPreflightPolicy.payload(permission: .authorized, inputAvailable: true)
  print("OPEN-DENIED=\(ListenPreflightPolicy.canOpen(permission: .denied, inputAvailable: true))")
  print("OPEN-GRANTED=\(ListenPreflightPolicy.canOpen(permission: .authorized, inputAvailable: true))")
  print("PREFLIGHT-UNKNOWN=\(notDetermined["permission"] as! String)/\(notDetermined["deviceState"] as! String)/\(notDetermined["recovery"] as! String)")
  print("PREFLIGHT-DENIED=\(denied["permission"] as! String)/\(denied["deviceState"] as! String)/\(denied["recovery"] as! String)")
  print("PREFLIGHT-GRANTED=\(granted["permission"] as! String)/\(granted["deviceState"] as! String)/\(granted["deviceLabel"] as! String)")
  print("OPEN-EVIDENCE=\(ListenPreflightPolicy.canOpen(permission: .denied, inputAvailable: false, evidenceAudioEnabled: true))")
  let evidence = ListenPreflightPolicy.payload(permission: .denied, inputAvailable: false, evidenceAudioEnabled: true)
  print("PREFLIGHT-EVIDENCE=\(evidence["permission"] as! String)/\(evidence["deviceState"] as! String)/\(evidence["deviceLabel"] as! String)")
  print("URL=\(prepared.request.url!.absoluteString)")
  let auth = prepared.request.value(forHTTPHeaderField: "Authorization") ?? "missing"
  print("AUTH=\(auth)")
  let clientId = prepared.request.value(forHTTPHeaderField: "x-omi-client-id") ?? "missing"
  print("CLIENT-ID=\(clientId)")
  let startCmd = try! JSONDecoder().decode(
    ListenSocketCommand.self, from: #"{"id":"listen-1","action":"start"}"#.data(using: .utf8)!)
  let stopCmd = try! JSONDecoder().decode(
    ListenSocketCommand.self, from: #"{"id":"listen-1","action":"stop"}"#.data(using: .utf8)!)
  print("CMD-START=\(startCmd.action)/\(startCmd.id)")
  print("CMD-STOP=\(stopCmd.action)")
  print("TEARDOWN-STOP=\(ListenCapturePolicy.tearsDownCapture("stop"))")
  print("TEARDOWN-CLOSE=\(ListenCapturePolicy.tearsDownCapture("close"))")
  print("TEARDOWN-OPEN=\(ListenCapturePolicy.tearsDownCapture("open"))")
  print("MIC-EVIDENCE=\(ListenCapturePolicy.shouldInstallTap(evidenceAudioEnabled: true))")
  print("MIC-LIVE=\(ListenCapturePolicy.shouldInstallTap(evidenceAudioEnabled: false))")
  print("REQUEST-NO-USAGE=\(ListenCapturePolicy.canRequestAccess(hasUsageDescription: false, evidenceAudioEnabled: false))")
  print("REQUEST-EVIDENCE=\(ListenCapturePolicy.canRequestAccess(hasUsageDescription: true, evidenceAudioEnabled: true))")
  print("REQUEST-LIVE=\(ListenCapturePolicy.canRequestAccess(hasUsageDescription: true, evidenceAudioEnabled: false))")
  print("CHUNK-BYTES=\(ListenPcm16.bytesPerChunk)")
  var leftover = Data(count: 5_000)
  let chunks = ListenPcm16.takeChunks(&leftover)
  print("CHUNKS=\(chunks.count)")
  print("REMAIN=\(leftover.count)")
  let identityFormat = ListenPcm16.targetFormat
  let identity = AVAudioPCMBuffer(pcmFormat: identityFormat, frameCapacity: 1_600)!
  identity.frameLength = 1_600
  let samples = identity.int16ChannelData![0]
  for i in 0..<1_600 { samples[i] = Int16(i - 800) }
  let identityConverter = AVAudioConverter(from: identityFormat, to: identityFormat)!
  let identityBytes = ListenPcm16.convert(identity, using: identityConverter)
  let first = Int16(bitPattern: UInt16(identityBytes[0]) | (UInt16(identityBytes[1]) << 8))
  let lastIndex = 1_599 * 2
  let last = Int16(
    bitPattern: UInt16(identityBytes[lastIndex]) | (UInt16(identityBytes[lastIndex + 1]) << 8))
  print("PCM-IDENTITY-BYTES=\(identityBytes.count)")
  print("PCM-IDENTITY-FIRST=\(first)")
  print("PCM-IDENTITY-LAST=\(last)")
  let sourceFormat = AVAudioFormat(
    commonFormat: .pcmFormatFloat32, sampleRate: 48_000, channels: 1, interleaved: false)!
  let source = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: 4_800)!
  source.frameLength = 4_800
  let resampleConverter = AVAudioConverter(from: sourceFormat, to: ListenPcm16.targetFormat)!
  let resampled = ListenPcm16.convert(source, using: resampleConverter)
  print("PCM-RESAMPLE-BYTES=\(resampled.count)")
  print("PCM-RESAMPLE-EVEN=\(resampled.count % 2 == 0)")
  exit(0)
}
print("FAIL")
exit(1)
`;

test(
  "macOS production socket composition targets the API authority with the shell bearer",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    // red-proof: send an empty/open-time probe or change the PCM formula; the
    // compiled native harness reports a different byte count/sample sequence.
    // Headless CI has no TCC and must not start AVAudioEngine; conversion,
    // chunking, start/stop vocabulary, and evidence-bypass policy are the
    // native units under test.
    const scratch = mkdtempSync(join(tmpdir(), "omi-listen-socket-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(root, "shell/Sources/OmiShell/BridgeHttpContract.generated.swift"),
        join(root, "shell/Sources/OmiShell/BridgeHttp.swift"),
        join(root, "shell/Sources/OmiShell/ListenSocket.swift"),
        join(root, "shell/Sources/OmiShell/ListenCapture.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "AppKit",
        "-framework", "AVFoundation",
        "-framework", "WebKit",
      ]);
      const output = execFileSync(binary, { encoding: "utf8" });
      const expectedPrefix = "AUDIO-BYTES=3200\nSAMPLE-0=-12000\nSAMPLE-1=-11743\nSAMPLE-1599=-9074\nREADY=true\nNOT-READY=false\nOPEN-DENIED=false\nOPEN-GRANTED=true\nPREFLIGHT-UNKNOWN=unknown/unknown/request-permission\nPREFLIGHT-DENIED=denied/unavailable/open-settings\nPREFLIGHT-GRANTED=granted/available/Default microphone\nOPEN-EVIDENCE=true\nPREFLIGHT-EVIDENCE=granted/available/Evidence audio\nURL=wss://staging.example.test/v4/listen?language=en\nAUTH=Bearer shell-token\nCLIENT-ID=run-listen-proof::macos\n";
      assert.equal(output.startsWith(expectedPrefix), true, output);
      assert.match(output, /^CMD-START=start\/listen-1$/m);
      assert.match(output, /^CMD-STOP=stop$/m);
      assert.match(output, /^TEARDOWN-STOP=true$/m);
      assert.match(output, /^TEARDOWN-CLOSE=true$/m);
      assert.match(output, /^TEARDOWN-OPEN=false$/m);
      assert.match(output, /^MIC-EVIDENCE=false$/m);
      assert.match(output, /^MIC-LIVE=true$/m);
      assert.match(output, /^REQUEST-NO-USAGE=false$/m);
      assert.match(output, /^REQUEST-EVIDENCE=false$/m);
      assert.match(output, /^REQUEST-LIVE=true$/m);
      assert.match(output, /^CHUNK-BYTES=3200$/m);
      assert.match(output, /^CHUNKS=1$/m);
      assert.match(output, /^REMAIN=1800$/m);
      assert.match(output, /^PCM-IDENTITY-BYTES=3200$/m);
      assert.match(output, /^PCM-IDENTITY-FIRST=-800$/m);
      assert.match(output, /^PCM-IDENTITY-LAST=799$/m);
      const resampled = Number(/PCM-RESAMPLE-BYTES=(\d+)/.exec(output)?.[1]);
      assert.equal(output.includes("PCM-RESAMPLE-EVEN=true"), true);
      assert.equal(resampled % 2, 0);
      assert.ok(
        resampled >= 2400 && resampled <= 4000,
        `48 kHz 100ms silence should resample near 3200 bytes, got ${resampled}`,
      );
      assert.equal(output.includes("127.0.0.1:5290"), false);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
