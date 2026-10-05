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
    platforms: [.iOS(.v17), .macOS(.v15)],
    products: [
        .library(name: "OmiKit", targets: ["OmiKit"]),
        .library(name: "OmiUI", targets: ["OmiUI"]),
    ],
    dependencies: [
        .package(url: "https://github.com/skiptools/skip.git", from: "1.9.11"),
        .package(url: "https://github.com/skiptools/skip-lib.git", from: "1.4.3"),
        .package(url: "https://github.com/skiptools/skip-foundation.git", from: "1.4.6"),
        .package(url: "https://github.com/skiptools/skip-ui.git", from: "1.60.0"),
        // OnboardingKit (danielsaidi, MIT) powers the onboarding cards on
        // Apple platforms. Skip cannot transpile it, so OmiUI imports it
        // only inside `#if !SKIP` and keeps a native rendering for Android.
        .package(
            url: "https://github.com/danielsaidi/OnboardingKit.git",
            from: "10.0.0"),
        // Inject (MIT) is a no-op outside Debug. It lets the macOS host
        // reload a saved SwiftUI file without restarting, once InjectionIII
        // is running. Skip cannot transpile it.
        .package(
            url: "https://github.com/krzysztofzablocki/Inject.git",
            from: "1.5.2"),
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
                "src/omi_device.cpp",
                "src/omi_auth.cpp",
                "src/omi_text.cpp",
            ],
            publicHeadersPath: "include",
            linkerSettings: [.linkedLibrary("bcrypt", .when(platforms: [.windows]))]
        ),
        .target(
            name: "OmiKit",
            dependencies: [
                "CNativeCore",
                .product(name: "SkipLib", package: "skip-lib"),
                .product(name: "SkipFoundation", package: "skip-foundation"),
            ],
            path: "app/Sources/OmiKit",
            plugins: [skipStone]
        ),
        .target(
            name: "OmiUI",
            dependencies: [
                "OmiKit",
                .product(name: "SkipUI", package: "skip-ui"),
                .product(name: "OnboardingKit", package: "onboardingkit"),
                .product(name: "Inject", package: "Inject"),
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
