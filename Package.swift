// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "omi-lib",
    platforms: [
        .iOS(.v17)  // Set minimum version to iOS 17
    ],
    products: [
        .library(
            name: "omi-lib",
            targets: ["omi-lib"]
        ),
    ],
    dependencies: [
        // Add your dependency here
        .package(url: "https://github.com/nelcea/swift-opus.git", from: "1.0.0"),
        .package(url: "https://github.com/exPHAT/SwiftWhisper.git", branch: "fast"),
        .package(url: "https://github.com/AudioKit/AudioKit.git", from: "5.6.4"),
    ],
    targets: [
        .target(
            name: "omi-lib",
            dependencies: [
                .product(name: "Opus", package: "swift-opus"),
                .product(name: "SwiftWhisper", package: "SwiftWhisper"),
                .product(name: "AudioKit", package: "AudioKit"),
            ],
            path: "sdks/swift",  // Correct the path to your source files
            resources: [
                .process("Sources/omi-lib/helpers/ggml-tiny.en.bin")  // Make sure this resource is in the correct directory
            ]
        ),
    ]
)
