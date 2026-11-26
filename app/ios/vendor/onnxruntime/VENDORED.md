# Vendored ONNX Runtime 1.23.0 podspecs

`onnxruntime-c` and `onnxruntime-objc` 1.23.0 (pulled in by `onnxruntime_v2`) are the only pods in
`app/ios/Podfile.lock` whose trunk podspecs download from `download.onnxruntime.ai`. On 2026-11-21 that
host served a `*.azureedge.net` certificate and returned 404 even with certificate checks off (the Azure
CDN behind it is gone, #25949). Every `pod install` without a warm CocoaPods cache failed, including the
iOS Compile Check.

The two `*.podspec.json` files here are the unchanged CocoaPods trunk specs for 1.23.0. Only `source`
changed: the archive URL points at the dependency-only release
[`mobile-build-deps-onnx-1.23.0`](https://github.com/BasedHardware/omi/releases/tag/mobile-build-deps-onnx-1.23.0),
plus a `sha256` that CocoaPods verifies before it extracts anything. The version, the binaries, the
headers and the build settings are the same as upstream.

## Provenance: these are re-zips, not the original bytes

No original archive could be found. `download.onnxruntime.ai` 404s, `github.com/microsoft/onnxruntime`
and `github.com/microsoft/onnxruntime-swift-package-manager` return 404 (so the SwiftPM checksum pins
cannot be read), and the Wayback Machine has no capture. The NuGet package
`Microsoft.ML.OnnxRuntime` 1.23.0 ships an iOS xcframework, but it is a separate build with different
bytes, so it cannot stand in for the pod.

Each archive was rebuilt from extracted copies of the original pod download. Two independent copies
matched on the sha256 of every file:

1. Codemagic's retained CocoaPods cache for the `ios-internal-auto` workflow
   (`Pods/Release/onnxruntime-c/1.23.0-3174c`, `Pods/Release/onnxruntime-objc/1.23.0-1254d`), exported
   by diagnostic build `6b01974140c3d46136563751`. That build had no signing, no secrets and no
   publishing, and it failed on purpose so the cache was not saved back. Files carry the upstream
   mtimes (Sep 26 2025).
2. `app/ios/Pods` on Omi's build Mac mini, installed from the upstream host on 2026-11-06.

- `onnxruntime-c`: all 52 files are identical. That covers the static `ios-arm64`,
  `ios-arm64_x86_64-simulator` and `macos-arm64_x86_64` slices, the xcframework `Info.plist`, the
  headers and `LICENSE`. The slices are static `ar` archives, so they have no LC_UUID to compare; the
  comparison is the whole-file sha256.
- `onnxruntime-objc`: the 25 files the app builds (`objectivec/` sources and headers, `LICENSE`) are
  identical. Codemagic's copy also holds 9 `objectivec/test/` files that only the podspec's test spec
  uses. They are included from that single source and are never compiled into the app.

The zips hold the files at the archive root (the layout CocoaPods extracts). Entries are sorted,
mtimes are kept, and the macOS framework symlinks are stored as links. Per-file manifests
(`*.files.sha256`) are attached to the release.

| Asset | sha256 |
| --- | --- |
| `pod-archive-onnxruntime-c-1.23.0.zip` | `9da435985bbdc61af74ad39e932b036b748e25a9245d28aed251b2bcc0bd813d` |
| `pod-archive-onnxruntime-objc-1.23.0.zip` | `6b70a6fbb362ccc2100da1a3a99be8f048ed76ad269e472d1db58741f86dd330` |

Never replace the release assets in place. A different version needs its own reviewed release, URLs
and checksums.

## Returning to upstream

When `download.onnxruntime.ai` (or another official source) serves the 1.23.0 archives again, or the
app moves to an onnxruntime version that has a working source: delete `omi_onnxruntime_mirror_pods`
and its two calls from `app/ios/Podfile`, run `pod install`, check that `Podfile.lock` lists both pods
under `SPEC REPOS` again, and delete this directory.
