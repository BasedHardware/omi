# Vendored onnxruntime-swift-package-manager

Source: `https://github.com/microsoft/onnxruntime-swift-package-manager` at
`b7fb7f7dea8a2469e6335d95a61b8f36d0dc83b2` (tag 1.24.2, the revision
`Desktop/Package.resolved` pinned). MIT licensed; see `LICENSE`.

Why: on 2026-11-18 the upstream repository started returning "Repository not
found", so every desktop build without a warm SwiftPM cache failed to resolve
packages. This is the wrapper only (Objective-C bindings and the manifest). The
ONNX Runtime binary is still fetched by `Package.swift` from
`download.onnxruntime.ai` and verified against its SHA256 checksum.

Left out of the copy: `.github/`, `.pipelines/`, `.config/` and
`objectivec/test/` (CI config and tests that the desktop app does not build).
Nothing else is modified.

Rollback: when upstream is reachable again (or a maintained source exists),
restore the `.package(url:...)` line in `Desktop/Package.swift`, re-resolve, and
delete this directory.
