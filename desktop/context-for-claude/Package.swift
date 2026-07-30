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
            dependencies: ["ContextCore"],
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
