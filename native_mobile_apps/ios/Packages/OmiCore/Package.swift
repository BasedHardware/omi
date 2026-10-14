// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiCore",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiCore", targets: ["OmiCore"]),
    ],
    targets: [
        .target(name: "OmiCore"),
        .testTarget(name: "OmiCoreTests", dependencies: ["OmiCore"]),
    ],
    swiftLanguageModes: [.v6]
)
