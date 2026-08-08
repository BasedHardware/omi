// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SwiftNativeShell",
    platforms: [.macOS(.v12)],
    products: [.executable(name: "SwiftNativeShell", targets: ["SwiftNativeShell"])],
    targets: [.executableTarget(name: "SwiftNativeShell")]
)
