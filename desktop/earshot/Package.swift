// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Earshot",
    platforms: [.macOS("14.4")],
    products: [
        .executable(name: "EarshotApp", targets: ["EarshotApp"]),
        .executable(name: "earshot-mcp", targets: ["EarshotMCP"]),
        .library(name: "EarshotCore", targets: ["EarshotCore"]),
    ],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift.git", from: "6.24.0"),
        // Tags were pulled upstream; pin the revision Omi desktop uses.
        .package(
            url: "https://github.com/FluidInference/FluidAudio.git",
            revision: "19600a485baa4998812e4654b70d2bab8f2c9949"
        ),
    ],
    targets: [
        // Storage, queries, and every pure policy the app and the MCP server share.
        .target(
            name: "EarshotCore",
            dependencies: [.product(name: "GRDB", package: "GRDB.swift")],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        // MCP protocol + tool dispatch, kept out of the executable so it is testable.
        .target(
            name: "EarshotMCPKit",
            dependencies: ["EarshotCore"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .executableTarget(
            name: "EarshotMCP",
            dependencies: ["EarshotMCPKit"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .executableTarget(
            name: "EarshotApp",
            dependencies: [
                "EarshotCore",
                .product(name: "FluidAudio", package: "FluidAudio"),
            ],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "EarshotCoreTests",
            dependencies: ["EarshotCore"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        .testTarget(
            name: "EarshotMCPKitTests",
            dependencies: ["EarshotMCPKit"],
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
    ]
)
