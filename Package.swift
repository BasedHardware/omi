// swift-tools-version: 6.1
import PackageDescription

// Omi v5 — Swift cross-platform app package (branch v5-swift).
//
// One shared package drives every native client:
//   - OmiKit   platform-neutral core: models, wire codecs, backend clients,
//              policy/codec facade over the C++ `native-core/` middleware
//   - OmiUI    shared SwiftUI (SkipUI-compatible) surfaces for iOS, Android
//              (via Skip transpilation), macOS, and the Windows host
//
// `CNativeCore` compiles the existing C++ middleware in `native-core/` in
// place — the codec, transport policy, HTTP plan facade, and recording rules
// stay C++ and are consumed through their C ABI (per user instruction, the
// middleware is not ported or duplicated).

let skipStone: Target.PluginUsage = .plugin(name: "skipstone", package: "skip")

let package = Package(
    name: "omi-v5",
    defaultLocalization: "en",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "OmiKit", targets: ["OmiKit"]),
        .library(name: "OmiUI", targets: ["OmiUI"]),
    ],
    dependencies: [
        .package(url: "https://github.com/skiptools/skip.git", from: "1.9.11"),
        .package(url: "https://github.com/skiptools/skip-lib.git", from: "1.4.3"),
        .package(url: "https://github.com/skiptools/skip-ui.git", from: "1.60.0"),
    ],
    targets: [
        .target(
            name: "CNativeCore",
            path: "native-core",
            sources: [
                "src/omi_native_boundary.cpp",
                "src/omi_backend_policy.cpp",
                "src/omi_backend_http.cpp",
                "src/omi_backend_recording.cpp",
            ],
            publicHeadersPath: "include"
        ),
        .target(
            name: "OmiKit",
            dependencies: [
                "CNativeCore",
                .product(name: "SkipLib", package: "skip-lib"),
            ],
            path: "app/Sources/OmiKit",
            plugins: [skipStone]
        ),
        .target(
            name: "OmiUI",
            dependencies: [
                "OmiKit",
                .product(name: "SkipUI", package: "skip-ui"),
            ],
            path: "app/Sources/OmiUI",
            plugins: [skipStone]
        ),
        .testTarget(
            name: "OmiKitTests",
            dependencies: ["OmiKit"],
            path: "app/Tests/OmiKitTests"
        ),
        .testTarget(
            name: "OmiUITests",
            dependencies: ["OmiUI"],
            path: "app/Tests/OmiUITests"
        ),
    ],
    cxxLanguageStandard: .cxx20
)
