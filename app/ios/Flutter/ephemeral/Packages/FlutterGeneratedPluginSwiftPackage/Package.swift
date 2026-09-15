// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.
//
// Generated file. Do not edit.
//

import PackageDescription

let package = Package(
    name: "FlutterGeneratedPluginSwiftPackage",
    platforms: [
        .iOS("13.0")
    ],
    products: [
        .library(name: "FlutterGeneratedPluginSwiftPackage", type: .static, targets: ["FlutterGeneratedPluginSwiftPackage"])
    ],
    dependencies: [
        .package(name: "app_links", path: "../.packages/app_links-6.4.1"),
        .package(name: "audio_session", path: "../.packages/audio_session-0.1.25"),
        .package(name: "connectivity_plus", path: "../.packages/connectivity_plus-6.1.5"),
        .package(name: "device_info_plus", path: "../.packages/device_info_plus-11.5.0"),
        .package(name: "disk_space_2", path: "../.packages/disk_space_2-1.0.12"),
        .package(name: "file_picker", path: "../.packages/file_picker-8.3.2"),
        .package(name: "firebase_auth", path: "../.packages/firebase_auth-5.5.3"),
        .package(name: "firebase_core", path: "../.packages/firebase_core-3.13.0"),
        .package(name: "firebase_crashlytics", path: "../.packages/firebase_crashlytics-4.3.2"),
        .package(name: "firebase_messaging", path: "../.packages/firebase_messaging-15.2.5"),
        .package(name: "flutter_native_splash", path: "../.packages/flutter_native_splash-2.4.7"),
        .package(name: "geolocator_apple", path: "../.packages/geolocator_apple-2.3.13"),
        .package(name: "image_picker_ios", path: "../.packages/image_picker_ios-0.8.13+3"),
        .package(name: "in_app_review", path: "../.packages/in_app_review-2.0.11"),
        .package(name: "integration_test", path: "../.packages/integration_test"),
        .package(name: "just_audio", path: "../.packages/just_audio-0.9.46"),
        .package(name: "package_info_plus", path: "../.packages/package_info_plus-8.3.1"),
        .package(name: "path_provider_foundation", path: "../.packages/path_provider_foundation-2.5.1"),
        .package(name: "posthog_flutter", path: "../.packages/posthog_flutter-5.28.0"),
        .package(name: "quick_actions_ios", path: "../.packages/quick_actions_ios-1.2.4"),
        .package(name: "share_plus", path: "../.packages/share_plus-11.0.0"),
        .package(name: "shared_preferences_foundation", path: "../.packages/shared_preferences_foundation-2.5.6"),
        .package(name: "sqflite_darwin", path: "../.packages/sqflite_darwin-2.4.2"),
        .package(name: "url_launcher_ios", path: "../.packages/url_launcher_ios-6.3.6"),
        .package(name: "video_player_avfoundation", path: "../.packages/video_player_avfoundation-2.8.8"),
        .package(name: "webview_flutter_wkwebview", path: "../.packages/webview_flutter_wkwebview-3.23.5"),
        .package(name: "FlutterFramework", path: "../.packages/FlutterFramework")
    ],
    targets: [
        .target(
            name: "FlutterGeneratedPluginSwiftPackage",
            dependencies: [
                .product(name: "app-links", package: "app_links"),
                .product(name: "audio-session", package: "audio_session"),
                .product(name: "connectivity-plus", package: "connectivity_plus"),
                .product(name: "device-info-plus", package: "device_info_plus"),
                .product(name: "disk-space-2", package: "disk_space_2"),
                .product(name: "file-picker", package: "file_picker"),
                .product(name: "firebase-auth", package: "firebase_auth"),
                .product(name: "firebase-core", package: "firebase_core"),
                .product(name: "firebase-crashlytics", package: "firebase_crashlytics"),
                .product(name: "firebase-messaging", package: "firebase_messaging"),
                .product(name: "flutter-native-splash", package: "flutter_native_splash"),
                .product(name: "geolocator-apple", package: "geolocator_apple"),
                .product(name: "image-picker-ios", package: "image_picker_ios"),
                .product(name: "in-app-review", package: "in_app_review"),
                .product(name: "integration-test", package: "integration_test"),
                .product(name: "just-audio", package: "just_audio"),
                .product(name: "package-info-plus", package: "package_info_plus"),
                .product(name: "path-provider-foundation", package: "path_provider_foundation"),
                .product(name: "posthog-flutter", package: "posthog_flutter"),
                .product(name: "quick-actions-ios", package: "quick_actions_ios"),
                .product(name: "share-plus", package: "share_plus"),
                .product(name: "shared-preferences-foundation", package: "shared_preferences_foundation"),
                .product(name: "sqflite-darwin", package: "sqflite_darwin"),
                .product(name: "url-launcher-ios", package: "url_launcher_ios"),
                .product(name: "video-player-avfoundation", package: "video_player_avfoundation"),
                .product(name: "webview-flutter-wkwebview", package: "webview_flutter_wkwebview"),
                .product(name: "FlutterFramework", package: "FlutterFramework")
            ]
        )
    ]
)
