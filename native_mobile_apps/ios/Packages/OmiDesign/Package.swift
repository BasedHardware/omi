// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "OmiDesign",
    defaultLocalization: "en",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiDesign", targets: ["OmiDesign"]),
    ],
    targets: [
        .target(
            name: "OmiDesign",
            resources: [.process("Resources/Localizable.xcstrings"), .copy("Resources/Media"), .copy("Resources/Fonts")]
        ),
        .testTarget(name: "OmiDesignTests", dependencies: ["OmiDesign"]),
    ],
    swiftLanguageModes: [.v6]
)
