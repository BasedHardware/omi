# Vendored universal libwebp dylibs

`libwebp.7.dylib` and `libsharpyuv.0.dylib` here are **universal (arm64 + x86_64)**
builds of [libwebp](https://chromium.googlesource.com/webm/libwebp) **1.5.0**.

## Why they are committed

The release pipeline (`codemagic.yaml` → `omi-desktop-swift-release`) builds a
universal Omi.app. Homebrew's `libwebp` on the Codemagic Mac mini m2 runners is
**arm64-only**, which breaks the x86_64 cross-compile link step. The pipeline
therefore needs universal `libwebp.7.dylib` + `libsharpyuv.0.dylib` to patch over
Homebrew's arm64-only copies.

Previously the "Prepare universal libwebp" step compiled libwebp **from source for
both arches on every release run** (~several minutes each run). These prebuilt
dylibs are vendored so that step just copies them instead. The from-source build
remains as an automatic fallback in `codemagic.yaml` if these files are missing or
not universal — so the pipeline stays fully reproducible from source.

## How to rebuild (exactly what the fallback / CI does)

```sh
WEBP_VERSION="1.5.0"
TEMP_DIR="$(mktemp -d)"
# version-min flags pin LC_BUILD_VERSION minos to 13.0; CMAKE_OSX_DEPLOYMENT_TARGET
# alone does NOT stick on newer SDKs (they stamp the SDK version, e.g. 26.0, which
# would refuse to load on older macOS). Verify with: otool -l <dylib> | grep -A3 LC_BUILD_VERSION
export MACOSX_DEPLOYMENT_TARGET=13.0
CMAKE_COMMON="-DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=13.0 \
  -DCMAKE_C_FLAGS=-mmacosx-version-min=13.0 \
  -DCMAKE_SHARED_LINKER_FLAGS=-mmacosx-version-min=13.0 \
  -DWEBP_BUILD_EXTRAS=OFF -DWEBP_BUILD_ANIM_UTILS=OFF \
  -DWEBP_BUILD_CWEBP=OFF -DWEBP_BUILD_DWEBP=OFF \
  -DWEBP_BUILD_GIF2WEBP=OFF -DWEBP_BUILD_IMG2WEBP=OFF \
  -DWEBP_BUILD_VWEBP=OFF -DWEBP_BUILD_WEBPINFO=OFF \
  -DWEBP_BUILD_WEBPMUX=OFF"
curl -sL "https://storage.googleapis.com/downloads.webmproject.org/releases/webp/libwebp-$WEBP_VERSION.tar.gz" | tar xz -C "$TEMP_DIR"
SRC="$TEMP_DIR/libwebp-$WEBP_VERSION"

mkdir "$SRC/build-arm64"  && (cd "$SRC/build-arm64"  && cmake .. -DCMAKE_OSX_ARCHITECTURES=arm64  $CMAKE_COMMON && make -j webp sharpyuv)
mkdir "$SRC/build-x86_64" && (cd "$SRC/build-x86_64" && cmake .. -DCMAKE_OSX_ARCHITECTURES=x86_64 $CMAKE_COMMON && make -j webp sharpyuv)

lipo -create \
  "$(find "$SRC/build-arm64"  -name 'libwebp.7.*.dylib'    -not -type l | head -1)" \
  "$(find "$SRC/build-x86_64" -name 'libwebp.7.*.dylib'    -not -type l | head -1)" \
  -output libwebp.7.dylib
lipo -create \
  "$(find "$SRC/build-arm64"  -name 'libsharpyuv.0.*.dylib' -not -type l | head -1)" \
  "$(find "$SRC/build-x86_64" -name 'libsharpyuv.0.*.dylib' -not -type l | head -1)" \
  -output libsharpyuv.0.dylib
```

Verify with `lipo -info libwebp.7.dylib` (expect `x86_64 arm64`). Both dylibs use
`@rpath` install names, identical to a fresh from-source build.

**When bumping the libwebp version**, update `WEBP_VERSION` in `codemagic.yaml`,
rebuild these two files with the steps above, and update this README.
