// swift-tools-version:5.3
import PackageDescription

let package = Package(
    name: "Omi",
    products: [
        .library(
            name: "OmiSDK",
            targets: ["OmiSDK"]
        ),
    ],
    targets: [
        .target(
            name: "OmiSDK",
            path: "sdks/swift"
        )
    ]
)
