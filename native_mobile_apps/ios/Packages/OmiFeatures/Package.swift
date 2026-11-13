// swift-tools-version: 6.0
import PackageDescription

/// One target per feature. Features depend on Core/Service/Design and the shared
/// OmiComponents target only; a feature never imports another feature (the app shell composes them).
let shared: [Target.Dependency] = [
    .product(name: "OmiCore", package: "OmiCore"),
    .product(name: "OmiService", package: "OmiService"),
    .product(name: "OmiDesign", package: "OmiDesign"),
    "OmiComponents",
]

let features = [
    "AuthFeature",
    "OnboardingFeature",
    "DeviceFeature",
    "TodayFeature",
    "ConversationsFeature",
    "TasksFeature",
    "MemoryFeature",
    "AgentFeature",
    "SettingsFeature",
]

let package = Package(
    name: "OmiFeatures",
    platforms: [.iOS(.v18), .macOS(.v14)],
    products: [
        .library(name: "OmiFeatures", targets: ["OmiComponents"] + features),
    ],
    dependencies: [
        .package(path: "../OmiDevice"),
        .package(path: "../OmiCore"),
        .package(path: "../OmiService"),
        .package(path: "../OmiDesign"),
    ],
    targets: [
        .target(name: "OmiComponents", dependencies: [
            .product(name: "OmiCore", package: "OmiCore"),
            .product(name: "OmiService", package: "OmiService"),
            .product(name: "OmiDesign", package: "OmiDesign"),
        ]),
    ] + features.map { name in
        .target(
            name: name,
            dependencies: ["DeviceFeature", "OnboardingFeature"].contains(name)
                ? shared + [.product(name: "OmiDevice", package: "OmiDevice")]
                : shared
        )
    },
    swiftLanguageModes: [.v6]
)
