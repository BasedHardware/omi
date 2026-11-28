// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiTestSupport",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiTestSupport", targets: ["OmiTestSupport"]),
    ],
    dependencies: [
        .package(path: "../OmiCore"),
        .package(path: "../OmiNetwork"),
        .package(path: "../OmiPersistence"),
    ],
    targets: [
        .target(name: "OmiTestSupport", dependencies: ["OmiCore", "OmiNetwork", "OmiPersistence"]),
    ],
    swiftLanguageModes: [.v6]
)
