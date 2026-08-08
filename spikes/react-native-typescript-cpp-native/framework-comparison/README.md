# Focused mobile framework spike

This spike is intentionally limited to four candidates:

- React Native + TypeScript
- Flutter
- Valdi
- Lynx / ReactLynx

The question is whether each can host the same TypeScript-first/native-function contract. A host build does not prove BLE, background execution, or physical-device behavior.

## Run the contract probe

```bash
python3 framework-comparison/run-probe.py
```

The probe is dependency-free and checks only the four candidate declarations and the shared contract shape. It is not a substitute for framework builds.

## Evidence levels

| Level | Meaning |
|---|---|
| `contract-probe` | Shared contract is represented and validated |
| `shell-built` | A framework shell was generated or built locally |
| `runtime-verified` | A real app/module ran on the target runtime |
| `research-only` | Source/docs inspected without runtime proof |

## Current status

| Candidate | Current evidence | Next gate |
|---|---|---|
| React Native | Android shell and relay contract are proven; iOS toolchain blocker remains | Build the same narrow native adapter on Android and iOS |
| Flutter | Existing parity baseline; analyzer/macOS shell proof exists | Exercise the shared contract through the existing Flutter host |
| Lynx | Bun/Rspeedy shell bundle builds; native-module runtime is not proven | Add one native function and run the Android host |
| Valdi | Module resolution passes; full agent check fails in build, lint, and tests | Complete clean Android Bazel build, then tests |

## Scope boundary

Do not add desktop or Rust frameworks back to this comparison unless the mobile candidates are first rejected by evidence. The useful next experiment is a real native binding, not another synthetic framework matrix.

See [`COMPARISON.md`](COMPARISON.md) for the detailed decision record.
