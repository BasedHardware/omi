// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiDevice",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiDevice", targets: ["OmiDevice"]),
    ],
    dependencies: [
        // Firmware updates over SMP/MCUboot (what the Flutter app's mcumgr_flutter wraps).
        .package(url: "https://github.com/NordicSemiconductor/IOS-nRF-Connect-Device-Manager", exact: "1.14.9"),
    ],
    targets: [
        .target(name: "OmiDevice", dependencies: [
            .product(name: "iOSMcuManagerLibrary", package: "IOS-nRF-Connect-Device-Manager"),
        ]),
        .testTarget(name: "OmiDeviceTests", dependencies: ["OmiDevice"]),
    ],
    swiftLanguageModes: [.v6]
)
