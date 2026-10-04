// swift-tools-version: 6.1
import PackageDescription

// Standalone host package for the Linux desktop app (do NOT wire into the
// repo-root Package.swift — hosts stay out of the shared package, mirroring
// how the macOS/iOS hosts live in xcodegen projects).
//
// Status: manifest written, never built on Linux (no Linux toolchain on the
// dev machine). The sources type-check on macOS against the omi package and
// OpenSwiftUI-spm — see README.md for exactly what was verified.
//
// On Linux, the OpenSwiftUI dependency must come from source
// (OpenSwiftUIProject/OpenSwiftUI) — the OpenSwiftUI-spm binary package only
// ships Apple-platform XCFrameworks. Swap the dependency below accordingly.
let package = Package(
    name: "omi-v5-linux",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "omi-linux-host", targets: ["OmiLinuxHost"])
    ],
    dependencies: [
        // The shared app package at the repository root (provides OmiKit+OmiUI).
        // Explicit `name` pins the reference identity so the host works from
        // any clone directory name.
        .package(name: "omi", path: "../../.."),
        // Binary integration (macOS compile checks only — see note above).
        .package(url: "https://github.com/OpenSwiftUIProject/OpenSwiftUI-spm.git", from: "0.19.1"),
    ],
    targets: [
        .executableTarget(
            name: "OmiLinuxHost",
            dependencies: [
                // By-name references resolve against the path dependency
                // regardless of its local directory identity.
                "OmiKit",
                "OmiUI",
                .product(name: "OpenSwiftUI", package: "OpenSwiftUI-spm"),
            ],
            path: "Sources"
        ),
    ]
)
