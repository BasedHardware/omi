// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Context for Claude",
    platforms: [.macOS("14.4")],
    products: [
        .executable(name: "ContextApp", targets: ["ContextApp"]),
        .executable(name: "context-for-claude-mcp", targets: ["ContextMCP"]),
        .library(name: "ContextCore", targets: ["ContextCore"]),
    ],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift.git", from: "6.24.0"),
        // Tags were pulled upstream; pin the revision Omi desktop uses.
        .package(
            url: "https://github.com/FluidInference/FluidAudio.git",
            revision: "19600a485baa4998812e4654b70d2bab8f2c9949"
        ),
        // The auto-updater. Same version constraint as `desktop/macos/Desktop/Package.swift`, so both
        // apps resolve the same audited Sparkle and a fix that lands for one is a fix for the other.
        // The *feed* and the *key* are emphatically not shared — see `Sources/ContextApp/Update/`.
        //
        // Sparkle ships to SwiftPM as a binary XCFramework, so this is the first dependency that puts
        // a real `Sparkle.framework` in `Contents/Frameworks/`. `scripts/build.sh` copies and re-signs
        // it; a build that skips either step produces a bundle that dyld refuses to launch at all.
        .package(url: "https://github.com/sparkle-project/Sparkle", from: "2.9.0"),
    ],
    targets: [
        // The portable decision rules, shared verbatim with the Windows CMake build in `windows/`.
        // Sources live under `core/` and are compiled twice on purpose: once here for the macOS
        // app and MCP binary, once by `core/CMakeLists.txt` for Windows and for CI on any host.
        .target(
            name: "ContextCoreCxx",
            path: "core",
            exclude: ["CMakeLists.txt", "README.md", "tests"],
            sources: ["src"],
            publicHeadersPath: "include"
        ),
        // Storage, queries, and every pure policy the app and the MCP server share.
        .target(
            name: "ContextCore",
            dependencies: [
                "ContextCoreCxx",
                .product(name: "GRDB", package: "GRDB.swift"),
            ],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        // MCP protocol + tool dispatch, kept out of the executable so it is testable.
        .target(
            name: "ContextMCPKit",
            dependencies: ["ContextCore"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .executableTarget(
            name: "ContextMCP",
            dependencies: ["ContextMCPKit"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .executableTarget(
            name: "ContextApp",
            dependencies: [
                "ContextCore",
                .product(name: "FluidAudio", package: "FluidAudio"),
                .product(name: "Sparkle", package: "Sparkle"),
            ],
            // The generated sounds. `Resources/Fonts` reaches the app the other way — loose files
            // copied by `scripts/build.sh` — because they are registered from a directory URL. The
            // sounds are opened by name, so they ride in the SwiftPM resource bundle instead, which
            // `build.sh` already copies into `Contents/Resources` along with every other `*.bundle`.
            // Declared here and nowhere else: undeclared, they never leave the source tree.
            resources: [.copy("../../Resources/Sounds")],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "ContextCoreTests",
            dependencies: ["ContextCore"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "ContextMCPKitTests",
            dependencies: ["ContextMCPKit"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "ContextAppTests",
            dependencies: ["ContextApp"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
