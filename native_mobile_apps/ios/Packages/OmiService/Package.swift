// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiService",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiService", targets: ["OmiService"]),
    ],
    dependencies: [
        .package(path: "../OmiCore"),
        .package(path: "../OmiNetwork"),
        .package(path: "../OmiPersistence"),
        .package(path: "../OmiDevice"),
        .package(path: "../OmiAudio"),
        .package(path: "../OmiTestSupport"),
    ],
    targets: [
        .target(name: "OmiService", dependencies: ["OmiCore", "OmiNetwork", "OmiPersistence", "OmiDevice", "OmiAudio"]),
        .testTarget(name: "OmiServiceTests", dependencies: ["OmiService", "OmiTestSupport", "OmiPersistence", "OmiDevice"]),
    ],
    swiftLanguageModes: [.v6]
)
