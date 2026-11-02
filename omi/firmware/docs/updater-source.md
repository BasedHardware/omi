# Exact updater source location

Checked public `BasedHardware/omi` task checkout and already-fetched `origin/main`, both `e86cda5abb0ea7ff942ac1bcd07261140953812c`. No fetch, package download or install was performed.

* App wrapper: `app/lib/pages/home/firmware_mixin.dart`. It imports `package:mcumgr_flutter/mcumgr_flutter.dart`; configuration at lines165–169 sets swap estimate0, eraseAppSettings true and pipelineDepth1, without an explicit update mode. Success callback lines195–204 marks firmware installed. This alone does not establish the native manager's confirmation timing.
* Declaration: `app/pubspec.yaml:88`, `mcumgr_flutter: ^0.4.2`.
* Exact lock: `app/pubspec.lock:1344–1351`, hosted package `mcumgr_flutter` version `0.4.2`, repository URL `https://pub.dev`, package SHA-256 `e19a5c420bdc20c831ffc4673a01b8fb1825fb3f42524cfc454a9862b20453f2`. This is hosted-package metadata, not evidence that the package source bytes have been retrieved or verified here. It is not a Git/path dependency.
* Native iOS lock: `app/ios/Podfile.lock:212,219` resolves `iOSMcuManagerLibrary`1.6. The plugin pod reports0.0.2; that is a distinct pod version, not the Dart package version. The lock refers to `.symlinks/plugins/mcumgr_flutter/ios`.

No tracked vendored `mcumgr` package path or submodule was found. Generated `app/.dart_tool/package_config.json`, `app/.flutter-plugins-dependencies`, `app/ios/.symlinks/plugins/mcumgr_flutter`, and `app/ios/Pods/iOSMcuManagerLibrary` are absent in this checkout. Default Dart package cache is absent and `PUB_CACHE` is unset. Expected local CocoaPods Release cache and Nordic Android Gradle artifact cache are also absent. Android manager version cannot be determined without the plugin/native dependency metadata.

Where to look on an existing successful developer/build machine: its configured `PUB_CACHE`, typically `~/.pub-cache/hosted/pub.dev/mcumgr_flutter-0.4.2/`, generated `package_config.json`/plugin symlink, and native Pods/resolved Gradle source. Supply the exact0.4.2 package archive (matching the locked package checksum) plus relevant native dependency source/lock metadata through an approved route. We need Dart wrapper, plugin Swift/Kotlin bridge and iOS manager1.6/resolved Android manager, not just today's upstream documentation.

Earlier exact GitHub source request returned **“Failed to fetch restricted URL”**. It was known not fetched and was not retried through another network route. This local monorepo/cache audit was independently authorized. Confirmation timing remains unknown; retrieving exact sources is a remaining access/source blocker, not permission to bypass the restriction.
