// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "omi-lib",
    platforms: [
        .iOS(.v17)  // Set minimum version to iOS 16
    ],
    products: [
        // Products define the executables and libraries a package produces, making them visible to other packages.
        .library(
            name: "omi-lib",
            targets: ["omi-lib"]),
    ],
    dependencies: [
        // Add your dependency here
        .package(url: "https://github.com/nelcea/swift-opus.git", from: "1.0.0"),
        .package(url: "https://github.com/exPHAT/SwiftWhisper.git", branch: "fast"),
        .package(url: "https://github.com/AudioKit/AudioKit.git", from: "5.6.4"),

    ],
    targets: [
        // Targets are the basic building blocks of a package, defining a module or a test suite.
        // Targets can depend on other targets in this package and products from dependencies.
        .target(
            name: "omi-lib",
            dependencies: [
                .product(name: "Opus", package: "swift-opus"),
                .product(name: "SwiftWhisper", package: "SwiftWhisper"),
                .product(name: "AudioKit", package: "AudioKit"),
            ],
            resources: [
                .process("ggml-tiny.en.bin")
            ]
        ),
    ]
)
