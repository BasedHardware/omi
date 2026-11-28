// swift-tools-version: 6.0
import PackageDescription

/// What the app shares with its extensions (widgets, Live Activities, the notification service):
/// the App Group snapshots, the Live Activity attributes and the decisions behind them. No
/// dependencies, so every extension links it without pulling in the app.
let package = Package(
    name: "OmiExtras",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiExtras", targets: ["OmiExtras"]),
    ],
    targets: [
        .target(name: "OmiExtras"),
        .testTarget(name: "OmiExtrasTests", dependencies: ["OmiExtras"]),
    ],
    swiftLanguageModes: [.v6]
)
