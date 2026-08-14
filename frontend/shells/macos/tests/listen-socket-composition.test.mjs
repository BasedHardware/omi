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
        main,
        "-framework", "Foundation",
        "-framework", "AppKit",
        "-framework", "AVFoundation",
        "-framework", "WebKit",
      ]);
      const output = execFileSync(binary, { encoding: "utf8" });
      assert.equal(output, "AUDIO-BYTES=3200\nSAMPLE-0=-12000\nSAMPLE-1=-11743\nSAMPLE-1599=-9074\nREADY=true\nNOT-READY=false\nOPEN-DENIED=false\nOPEN-GRANTED=true\nPREFLIGHT-UNKNOWN=unknown/unknown/request-permission\nPREFLIGHT-DENIED=denied/unavailable/open-settings\nPREFLIGHT-GRANTED=granted/available/Default microphone\nOPEN-EVIDENCE=true\nPREFLIGHT-EVIDENCE=granted/available/Evidence audio\nURL=wss://staging.example.test/v4/listen?language=en\nAUTH=Bearer shell-token\nCLIENT-ID=run-listen-proof::macos\n");
      assert.equal(output.includes("127.0.0.1:5290"), false);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
