# Vendored onnxruntime-swift-package-manager

Source: `https://github.com/microsoft/onnxruntime-swift-package-manager` at
`b7fb7f7dea8a2469e6335d95a61b8f36d0dc83b2` (tag 1.24.2, the revision
`Desktop/Package.resolved` pinned). MIT licensed; see `LICENSE`.

Why: on 2026-11-18 the upstream repository started returning "Repository not
found", so every desktop build without a warm SwiftPM cache failed to resolve
packages. This is the wrapper only (Objective-C bindings and the manifest). The
ONNX Runtime binaries are fetched by `Package.swift` from the dependency-only
[GitHub release mirror](https://github.com/BasedHardware/omi/releases/tag/desktop-build-deps-onnx-1.24.2-extensions-0.13.0)
and verified against the unchanged upstream SHA256 checksums.

Left out of the copy: `.github/`, `.pipelines/`, `.config/` and
`objectivec/test/` (CI config and tests that the desktop app does not build).
Only the two binary-target download URLs are modified.

## Binary archive provenance

On 2026-11-21, `download.onnxruntime.ai` failed TLS hostname validation and
the alternate official storage endpoints did not serve these archive versions
(#25916). The original archives were recovered from Omi's retained Codemagic
SwiftPM cache by diagnostic build `6b0131aa0b93a529371ee052`. Both recovered
files independently matched the SHA256 pins already present in this manifest:

| Archive | SHA256 |
| --- | --- |
| `pod-archive-onnxruntime-c-1.24.2.zip` | `f7100a992d2a8135168c8afd831e6a58b465349101982aa58b3e11d36e600b54` |
| `pod-archive-onnxruntime-extensions-c-0.13.0.zip` | `346522d1171d4c99cb0908fa8e4e9330a4a6aad39cd83ce36eb654437b33e6b5` |

The mirrored archives are byte-for-byte originals, include their LICENSE files,
and contain both arm64 and x86_64 macOS slices. No rebuild, repack, version bump,
TLS bypass, or checksum change was made. SwiftPM continues to fail closed on a
checksum mismatch. Preserve the assets; never replace them in place. Future
dependency updates require separately reviewed versions, URLs and checksums.

Rollback: when upstream is reachable again (or a maintained source exists),
restore the `.package(url:...)` line in `Desktop/Package.swift`, re-resolve, and
delete this directory.
