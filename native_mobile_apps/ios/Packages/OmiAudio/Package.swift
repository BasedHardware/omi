// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiAudio",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiAudio", targets: ["OmiAudio"]),
    ],
    dependencies: [
        // Same opus decoder as upstream `sdks/swift` (Package.swift at the omi repo root).
        .package(url: "https://github.com/nelcea/swift-opus.git", from: "1.0.0"),
    ],
    targets: [
        .target(name: "OmiAudio", dependencies: [.product(name: "Opus", package: "swift-opus")]),
        .testTarget(name: "OmiAudioTests", dependencies: ["OmiAudio", .product(name: "Opus", package: "swift-opus")]),
    ],
    swiftLanguageModes: [.v6]
)
