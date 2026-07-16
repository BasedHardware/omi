// swift-tools-version: 6.0
import PackageDescription

let package = Package(
  name: "Omi Computer",
  platforms: [
    .macOS("14.0")
  ],
  dependencies: [
    .package(url: "https://github.com/firebase/firebase-ios-sdk.git", from: "11.0.0"),
    .package(url: "https://github.com/PostHog/posthog-ios.git", from: "3.0.0"),
    .package(url: "https://github.com/getsentry/sentry-cocoa.git", exact: "8.58.0"),
    .package(url: "https://github.com/groue/GRDB.swift.git", from: "6.24.0"),
    .package(url: "https://github.com/sparkle-project/Sparkle", from: "2.9.0"),
    .package(url: "https://github.com/gonzalezreal/swift-markdown-ui", from: "2.4.0"),
    .package(
      url: "https://github.com/microsoft/onnxruntime-swift-package-manager.git", from: "1.20.0"),
    .package(url: "https://github.com/FluidInference/FluidAudio.git", from: "0.14.8"),
  ],
  targets: [
    .target(
      name: "ObjCExceptionCatcher",
      path: "ObjCExceptionCatcher",
      publicHeadersPath: "include"
    ),
    .systemLibrary(
      name: "CWebP",
      path: "CWebP",
      pkgConfig: "libwebp",
      providers: [
        .brew(["webp"])
      ]
    ),
    .target(
      name: "OmiSupport",
      path: "Sources/OmiSupport",
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .target(
      name: "OmiTheme",
      path: "Sources/Theme",
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .target(
      name: "OmiWAL",
      path: "Sources/OmiWAL",
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .target(
      name: "VoiceTurnDomain",
      path: "Sources/VoiceTurnDomain",
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .executableTarget(
      name: "Omi Computer",
      dependencies: [
        "ObjCExceptionCatcher",
        "CWebP",
        "OmiSupport",
        "OmiTheme",
        "OmiWAL",
        "VoiceTurnDomain",
        .product(name: "FirebaseCore", package: "firebase-ios-sdk"),
        .product(name: "FirebaseAuth", package: "firebase-ios-sdk"),
        .product(name: "PostHog", package: "posthog-ios"),
        .product(name: "Sentry", package: "sentry-cocoa"),
        .product(name: "GRDB", package: "GRDB.swift"),
        .product(name: "Sparkle", package: "Sparkle"),
        .product(name: "MarkdownUI", package: "swift-markdown-ui"),
        .product(name: "onnxruntime", package: "onnxruntime-swift-package-manager"),
        .product(name: "FluidAudio", package: "FluidAudio"),
      ],
      path: "Sources",
      exclude: [
        "GoogleService-Info-Dev.plist",
        "GoogleService-Info-Local.plist",
        "Theme",
        "OmiSupport",
        "OmiWAL",
        "VoiceTurnDomain",
        "Bluetooth/ARCHITECTURE.md",
      ],
      resources: [
        .process("GoogleService-Info.plist"),
        // Bundles everything under Resources/ (incl. *_logo.png brand marks).
        // NOTE: SwiftPM caches the resource manifest, so new files added to
        // Resources/ are only picked up when the manifest regenerates — editing
        // this file forces incremental builds to re-scan and include them.
        .process("Resources"),
      ],
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .testTarget(
      name: "Omi ComputerTests",
      dependencies: [
        .target(name: "Omi Computer"),
        "OmiSupport",
        "OmiTheme",
        "OmiWAL",
        "VoiceTurnDomain",
      ],
      path: "Tests",
      exclude: [
        "fixtures",
        "SemanticFeatureSentinels",
        "OmiSupportTests",
        "OmiWALTests",
        "VoiceTurnDomainTests",
      ],
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .testTarget(
      name: "OmiSupportTests",
      dependencies: ["OmiSupport"],
      path: "Tests/OmiSupportTests",
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .testTarget(
      name: "OmiWALTests",
      dependencies: ["OmiWAL"],
      path: "Tests/OmiWALTests",
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete", "-warnings-as-errors"])
      ]
    ),
    .testTarget(
      name: "VoiceTurnDomainTests",
      dependencies: [
        .target(name: "Omi Computer"),
        "VoiceTurnDomain",
      ],
      path: "Tests/VoiceTurnDomainTests"
    ),
    .testTarget(
      name: "SemanticFeatureSentinels",
      dependencies: [],
      path: "Tests/SemanticFeatureSentinels",
      swiftSettings: [
        .unsafeFlags(["-strict-concurrency=complete"]),
      ]
    ),
  ],
  swiftLanguageModes: [.v6]
)
