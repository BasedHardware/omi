# Framework comparison spike

## Question

Can each candidate host the same TypeScript-first/native-function contract without pretending that a host-side contract test proves a native UI, BLE, or background runtime?

## Run

```bash
python3 framework-comparison/run-probe.py
```

The probe is dependency-free. It validates that every candidate has an explicit language, mobile/desktop target declaration, and native-boundary shape. It is deliberately not a fake framework build.

## Included candidates

- React Native + TypeScript
- Flutter
- Valdi
- Tauri
- Dioxus
- Crepuscularity
- Electrobun
- Jetpack Compose Multiplatform
- Lynx / ReactLynx
- Makepad
- Swift native (iOS/macOS only; Android intentionally excluded)
- Web TypeScript + Moonshine boundary

The detailed comparison and decision record is in [`COMPARISON.md`](COMPARISON.md).

## Local crate reuse check

The sibling crates were inspected as architecture references, not copied into this
spike:

- `~/projects/rotary` (`rx4`) is an agent-harness engine. Its `mcp` feature,
  `src/mcp.rs`, IPC, permissions, and session APIs could support a future host-side
  tool/agent integration, but they are not UI framework or native-function proof.
- `~/projects/zkr` is a Rust evidence-backed memory database. It could be an
  optional host persistence adapter in a later experiment, but using it here would
  violate this spike's no-production-code/no-Omi-v4-reuse boundary.

The framework decision remains independent of these crates. See the crate-specific
section in `COMPARISON.md` for the reuse boundary.

## Evidence levels

| Level | Meaning |
|---|---|
| `contract-probe` | Shared contract is represented and validated by the dependency-free probe |
| `shell-built` | A framework shell was generated/built in this repository |
| `runtime-verified` | A real framework app/module was executed on a target runtime |
| `research-only` | Docs/source inspected; no runtime claim |

The current probe is a comparison harness, not permission to claim that Lynx, Makepad, Valdi, Tauri, Dioxus, Electrobun, Compose, or Swift has passed a real Omi/native runtime test.

## Next discriminating builds

1. **Valdi or Lynx:** build one TypeScript screen plus one native-function binding.
2. **Makepad or Dioxus:** build one Rust screen plus the same native-function contract.
3. **Tauri, Electrobun, and Crepuscularity:** build one desktop screen plus the same contract.
4. **Compose:** build Android/iOS only; no Swift-for-Android claim.
5. **Swift native:** iOS/macOS only; Android is intentionally out of scope.

Each build must report its own toolchain blockers and must not be collapsed into the host relay result.
