// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiNetwork",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiNetwork", targets: ["OmiNetwork"]),
    ],
    dependencies: [
        .package(path: "../OmiCore"),
    ],
    targets: [
        .target(name: "OmiNetwork", dependencies: ["OmiCore"]),
        .testTarget(name: "OmiNetworkTests", dependencies: ["OmiNetwork"]),
    ],
    swiftLanguageModes: [.v6]
)
