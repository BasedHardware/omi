// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiPersistence",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiPersistence", targets: ["OmiPersistence"]),
    ],
    targets: [
        .target(name: "OmiPersistence"),
        .testTarget(name: "OmiPersistenceTests", dependencies: ["OmiPersistence"]),
    ],
    swiftLanguageModes: [.v6]
)
