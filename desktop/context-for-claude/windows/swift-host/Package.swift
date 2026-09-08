// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ContextWindowsHost",
    products: [
        .executable(name: "context-windows-host", targets: ["ContextWindowsHost"]),
    ],
    dependencies: [
        .package(name: "WinRTProjection", path: "projection"),
    ],
    targets: [
        .target(
            name: "CContextCore",
            path: "Sources/CContextCore",
            publicHeadersPath: "include"
        ),
        .executableTarget(
            name: "ContextWindowsHost",
            dependencies: [
                "CContextCore",
                .product(name: "WindowsFoundation", package: "WinRTProjection"),
            ],
            path: "Sources/ContextWindowsHost"
        ),
    ]
)
