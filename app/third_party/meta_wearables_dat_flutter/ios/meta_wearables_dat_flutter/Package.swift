// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to
// build this package. Flutter 3.24+ uses Swift Package Manager to resolve
// plugin Swift dependencies when the user runs
// `flutter config --enable-swift-package-manager`.

import PackageDescription

let package = Package(
  name: "meta_wearables_dat_flutter",
  platforms: [
    .iOS("17.0"),
  ],
  products: [
    .library(
      name: "meta-wearables-dat-flutter",
      targets: ["meta_wearables_dat_flutter"]
    ),
  ],
  dependencies: [
    .package(
      url: "https://github.com/facebook/meta-wearables-dat-ios",
      from: "0.7.0"
    ),
  ],
  targets: [
    .target(
      name: "meta_wearables_dat_flutter",
      dependencies: [
        .product(name: "MWDATCore", package: "meta-wearables-dat-ios"),
        .product(name: "MWDATCamera", package: "meta-wearables-dat-ios"),
        .product(name: "MWDATDisplay", package: "meta-wearables-dat-ios"),
      ],
      resources: []
    ),
  ]
)
