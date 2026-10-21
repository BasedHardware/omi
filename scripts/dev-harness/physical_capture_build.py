#!/usr/bin/env python3
"""Build the real Flutter capture lane as an isolated, signed iOS application.

Generated projects, receipts, signing settings and products stay outside Git.
This tool never installs or launches an application. It deliberately omits
unrelated app extensions, shared entitlements and external telemetry plugins.
"""

import argparse
import base64
import hashlib
import ipaddress
import json
import plistlib
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


EXCLUDED_PLUGINS = {
    "firebase_crashlytics": "FLTFirebaseCrashlyticsPlugin",
    "firebase_messaging": "FLTFirebaseMessagingPlugin",
    "intercom_flutter": "IntercomFlutterPlugin",
    "posthog_flutter": "PosthogFlutterPlugin",
}


def private_host(host):
    address = ipaddress.ip_address(host)
    networks = tuple(ipaddress.ip_network(value) for value in
                     ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"))
    if not (address.is_loopback or any(address in network for network in networks)):
        raise ValueError("fixture host must be a literal private or loopback IP")
    return host


def run(command, cwd, log):
    with log.open("w") as stream:
        result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text()[-10000:])
        raise SystemExit(f"Command failed ({result.returncode}); see {log}")


def hash_tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def input_hashes(app):
    result = {"lib/" + name: digest for name, digest in hash_tree(app / "lib").items()}
    for name in ("integration_test/physical_capture_main.dart",
                 "integration_test/support/physical_capture_lifecycle.dart", "pubspec.yaml", "pubspec.lock",
                 ".dart_tool/package_config.json", ".dev.env", ".env"):
        path = app / name
        if path.exists():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def refresh_runner_sources(source, destination):
    """Refresh this builder's generated copy, including source deletions."""
    if destination.is_symlink():
        raise RuntimeError("Generated Runner must not be a symlink")
    if destination.exists():
        for path in sorted(destination.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            original = source / path.relative_to(destination)
            if path.is_symlink():
                path.unlink()
            elif path.is_file() and not original.is_file():
                path.unlink()
            elif path.is_dir() and not original.is_dir():
                shutil.rmtree(path)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def adopt_capture_scene_lifecycle(runner):
    """Adapt only the generated host to Flutter's implicit-engine scene API.

    The original app's registration body stays intact, with its controller
    messenger/registry references redirected to the actual implicit engine.
    """
    delegate = runner / "AppDelegate.swift"
    source = delegate.read_text()
    class_marker = "@objc class AppDelegate: FlutterAppDelegate {"
    start_marker = "  override func application(\n    _ application: UIApplication,\n    didFinishLaunchingWithOptions"
    registration_marker = "    GeneratedPluginRegistrant.register(with: self)"
    end_marker = "  /// Swaps the engine-less storyboard controller"
    if any(source.count(marker) != 1 for marker in (class_marker, start_marker, registration_marker, end_marker)):
        raise RuntimeError("Runner AppDelegate shape changed; review scene-host adaptation before building")
    start = source.index(start_marker)
    end = source.index(end_marker)
    registration = source[source.index(registration_marker):end]
    registration = registration.replace("GeneratedPluginRegistrant.register(with: self)",
                                        "GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)")
    registration = registration.replace("controller.binaryMessenger", "captureMessenger")
    registration = registration.replace('self.registrar(forPlugin: "OmiPhoneCallsPlugin")',
                                        'engineBridge.pluginRegistry.registrar(forPlugin: "OmiPhoneCallsPlugin")')
    registration = registration.replace("      return true // Returning true will stop the propagation to other packages\n", "")
    registration = registration.replace("    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)\n", "")
    registration = registration.replace("    return launched\n", "")
    replacement = '''  private var captureLaunchOptions: [UIApplication.LaunchOptionsKey: Any]?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    captureLaunchOptions = launchOptions
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    let captureMessenger = engineBridge.applicationRegistrar.messenger()
    let launchOptions = captureLaunchOptions
'''
    source = source[:start] + replacement + registration + source[end:]
    source = source.replace(class_marker,
                            "@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {")
    if "controller.binaryMessenger" in source:
        raise RuntimeError("Scene-host adaptation left a controller-bound messenger")
    delegate.write_text(source)
    (runner / "CaptureQualificationSceneDelegate.swift").write_text('''import Flutter
import UIKit
import BackgroundTasks

// Qualification-host adaptation only. Flutter owns the real storyboard,
// engine, plugin scene forwarding, and view hierarchy.
class CaptureQualificationSceneDelegate: FlutterSceneDelegate {
  override func scene(_ scene: UIScene, willConnectTo session: UISceneSession,
                      options connectionOptions: UIScene.ConnectionOptions) {
    super.scene(scene, willConnectTo: session, options: connectionOptions)
    (UIApplication.shared.delegate as? AppDelegate)?.window = window
  }

  override func sceneDidEnterBackground(_ scene: UIScene) {
    UIApplication.shared.isIdleTimerDisabled = false
    super.sceneDidEnterBackground(scene)
    OmiBleManager.shared.markBackgroundTelemetryStart()
    BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: "com.pravera.flutter_foreground_task.refresh")
  }

  override func sceneDidBecomeActive(_ scene: UIScene) {
    UIApplication.shared.isIdleTimerDisabled = true
    OmiBleManager.shared.markBackgroundTelemetryEnd()
    super.sceneDidBecomeActive(scene)
  }

  override func sceneWillResignActive(_ scene: UIScene) {
    UIApplication.shared.isIdleTimerDisabled = false
    super.sceneWillResignActive(scene)
  }

  override func sceneWillEnterForeground(_ scene: UIScene) {
    super.sceneWillEnterForeground(scene)
    OmiBleManager.shared.reconnectStalePeripherals()
  }
}
''')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--flutter-root", type=Path, required=True)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--team", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--auth-host", required=True)
    parser.add_argument("--auth-port", type=int, required=True)
    parser.add_argument("--fixture-uid", required=True)
    parser.add_argument("--capture-seconds", type=int, default=20)
    parser.add_argument("--capture-source", choices=("phone_mic", "wearable"), default="phone_mic")
    parser.add_argument("--wearable-id", help="Optional discovered wearable ID for the real BLE capture scenario")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.wearable_id:
        args.capture_source = "wearable"
    app, output = args.app.resolve(), args.output.resolve()
    if ".capture-qualification." not in args.bundle_id:
        parser.error("bundle ID must contain .capture-qualification.")
    if app.parent == output or app.parent in output.parents:
        parser.error("output must be outside the product repository")
    api = urlparse(args.api_url)
    if api.scheme != "http" or api.username or api.password or api.query or api.fragment or api.path not in ("", "/"):
        parser.error("API must be a plain HTTP private fixture URL")
    private_host(api.hostname)
    private_host(args.auth_host)
    args.api_url = args.api_url.rstrip("/") + "/"
    if not args.fixture_uid.startswith("omi-physical-fixture-"):
        parser.error("fixture UID must start with omi-physical-fixture-")
    profile = plistlib.loads(subprocess.check_output(["security", "cms", "-D", "-i", str(args.profile)]))
    if args.team not in profile["TeamIdentifier"]:
        parser.error("profile team does not match --team")
    # Apple exposes development identities as SHA-1 certificate fingerprints.
    # Ask the platform certificate tool for that opaque identifier instead of
    # using an in-process weak hash that could be mistaken for a security digest.
    certificate_fingerprints = set()
    developer_certificates = profile.get("DeveloperCertificates", [])
    openssl = shutil.which("openssl") if developer_certificates else None
    if developer_certificates and openssl is None:
        parser.error("openssl is required to read Apple certificate fingerprints")
    for cert in developer_certificates:
        fingerprint = subprocess.check_output(
            [openssl, "x509", "-inform", "DER", "-fingerprint", "-sha1", "-noout"],
            input=cert,
            stderr=subprocess.STDOUT,
            text=True,
        ).strip().rsplit("=", 1)[-1]
        certificate_fingerprints.add(fingerprint.replace(":", "").upper())
    if args.identity.upper() not in certificate_fingerprints:
        parser.error("--identity must be the SHA-1 fingerprint of a certificate authorized by the profile")
    profile_app = profile["Entitlements"]["application-identifier"]
    if not re.fullmatch(re.escape(profile_app).replace(r"\*", ".*"), args.team + "." + args.bundle_id):
        parser.error("profile does not authorize the isolated bundle identifier")
    ios = output / "project" / "ios"
    ios.mkdir(parents=True, exist_ok=True)
    previous_plugins_path = ios.parent / ".flutter-plugins-dependencies"
    previous_plugins = json.loads(previous_plugins_path.read_text()) if previous_plugins_path.exists() else {}
    previous_flutter = (ios / "Flutter/Generated.xcconfig").read_text() if (ios / "Flutter/Generated.xcconfig").exists() else ""
    (output / "build-receipt.json").write_text(json.dumps({
        "built": False, "installed": False, "phase": "preparing", "app_source": str(app),
        "bundle_id": args.bundle_id,
    }, indent=2) + "\n")
    run(["env", "OMI_APP_PROFILE=local_dev", "bash", "scripts/validate_mobile_build_config.sh",
         "--flavor", "dev", "--profile", "local_dev"], app, output / "build-config-validation.log")
    runner = ios / "Runner"
    refresh_runner_sources(app / "ios" / "Runner", runner)
    adopt_capture_scene_lifecycle(runner)
    # These files must never be bundled or used for isolated signing.
    for path in runner.rglob("*.entitlements"):
        path.unlink()
    for path in runner.rglob("GoogleService-Info.plist"):
        path.unlink()
    registry = runner / "GeneratedPluginRegistrant.m"
    text = registry.read_text()
    for plugin, klass in EXCLUDED_PLUGINS.items():
        text = re.sub(r"#if __has_include\(<" + plugin + r"/.*?#endif\n", "", text, flags=re.S)
        text = re.sub(r"^.*\[" + klass + r" registerWithRegistrar:.*\n", "", text, flags=re.M)
    registry.write_text(text)
    for plugin, klass in EXCLUDED_PLUGINS.items():
        if plugin in text or klass in text:
            raise RuntimeError(f"Excluded SDK remains in generated registry: {plugin}")
    plugins = json.loads((app / ".flutter-plugins-dependencies").read_text())
    plugins["plugins"]["ios"] = [p for p in plugins["plugins"]["ios"] if p["name"] not in EXCLUDED_PLUGINS]
    plugins.setdefault("swift_package_manager_enabled", {})["ios"] = False
    (ios.parent / ".flutter-plugins-dependencies").write_text(json.dumps(plugins))
    plist = plistlib.loads((runner / "Info.plist").read_bytes())
    for key in ("CFBundleURLTypes", "MWDAT", "WKCompanionAppBundleIdentifier"):
        plist.pop(key, None)
    plist.update({
        "CFBundleDisplayName": "OmiCaptureQA", "CFBundleName": "OmiCaptureQA",
        "FirebaseMessagingAutoInitEnabled": False,
        "FirebaseCrashlyticsCollectionEnabled": False,
        "FirebaseDataCollectionDefaultEnabled": False,
        "FirebaseAppDelegateProxyEnabled": False,
        "com.posthog.posthog.AUTO_INIT": False,
        "OmiPhysicalAuthEmulatorHost": args.auth_host,
        "OmiPhysicalAuthEmulatorPort": args.auth_port,
        "OmiPhysicalAPIHost": api.hostname,
        "OmiPhysicalAPIPort": api.port or 80,
        "UIApplicationSceneManifest": {
            "UIApplicationSupportsMultipleScenes": False,
            "UISceneConfigurations": {"UIWindowSceneSessionRoleApplication": [{
                "UISceneClassName": "UIWindowScene", "UISceneConfigurationName": "flutter",
                "UISceneDelegateClassName": "$(PRODUCT_MODULE_NAME).CaptureQualificationSceneDelegate",
                "UISceneStoryboardFile": "Main",
            }]},
        },
        "UIBackgroundModes": ["audio", "bluetooth-central", "fetch", "processing"],
        "UIFileSharingEnabled": True, "LSSupportsOpeningDocumentsInPlace": True,
        "NSLocalNetworkUsageDescription": "Connect to the private capture qualification fixture.",
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True, "NSAllowsArbitraryLoads": True},
    })
    (ios / "Info.plist").write_bytes(plistlib.dumps(plist))
    defines = {
        "OMI_PHYSICAL_QUALIFICATION": "true", "OMI_APP_PROFILE": "local_dev",
        "OMI_API_BASE_URL": args.api_url,
        "OMI_FIREBASE_AUTH_EMULATOR_HOST": args.auth_host,
        "OMI_FIREBASE_AUTH_EMULATOR_PORT": str(args.auth_port),
        "OMI_PHYSICAL_FIXTURE_UID": args.fixture_uid,
        "OMI_PHYSICAL_CAPTURE_SECONDS": str(args.capture_seconds),
        "OMI_PHYSICAL_CAPTURE_SOURCE": args.capture_source,
    }
    if args.wearable_id:
        defines["OMI_PHYSICAL_WEARABLE_ID"] = args.wearable_id
    flutter = ios / "Flutter"
    flutter.mkdir(exist_ok=True)
    shutil.copy(app / "ios" / "Flutter" / "AppFrameworkInfo.plist", flutter)
    settings = {
        "FLUTTER_ROOT": str(args.flutter_root.resolve()), "FLUTTER_APPLICATION_PATH": str(app),
        "FLUTTER_TARGET": "integration_test/physical_capture_main.dart",
        "FLUTTER_BUILD_DIR": str(output / "flutter-build"), "FLUTTER_BUILD_MODE": "profile",
        "FLUTTER_BUILD_NAME": "1.0.0", "FLUTTER_BUILD_NUMBER": "1",
        "PACKAGE_CONFIG": str(app / ".dart_tool" / "package_config.json"),
        "DART_DEFINES": ",".join(base64.b64encode(f"{k}={v}".encode()).decode() for k, v in defines.items()),
        "DART_OBFUSCATION": "false", "TRACK_WIDGET_CREATION": "false", "TREE_SHAKE_ICONS": "false",
    }
    (flutter / "Generated.xcconfig").write_text("\n".join(f"{k}={v}" for k, v in settings.items()) + "\n")
    (flutter / "Profile.xcconfig").write_text('#include? "../Pods/Target Support Files/Pods-Runner/Pods-Runner.profile.xcconfig"\n#include "Generated.xcconfig"\n')
    sources = [{"path": str(p.relative_to(ios))} for p in runner.rglob("*") if p.suffix in (".swift", ".m", ".h")]
    # XcodeGen does not expand a Base.lproj directory supplied as a source.
    # List the localized storyboards explicitly so ibtool compiles and links
    # them into the app instead of leaving an untyped directory reference.
    sources += [{"path": f"Runner/Base.lproj/{name}.storyboard", "buildPhase": "resources"}
                for name in ("Main", "LaunchScreen")]
    sources += [{"path": "Runner/Assets.xcassets"}]
    target_settings = {
        "PRODUCT_BUNDLE_IDENTIFIER": args.bundle_id, "PRODUCT_NAME": "OmiCaptureQA",
        "DEVELOPMENT_TEAM": args.team, "CODE_SIGN_STYLE": "Manual",
        "CODE_SIGN_IDENTITY": args.identity, "PROVISIONING_PROFILE_SPECIFIER": profile["UUID"],
        "INFOPLIST_FILE": "Info.plist", "GENERATE_INFOPLIST_FILE": "NO",
        "SWIFT_OBJC_BRIDGING_HEADER": "Runner/Runner-Bridging-Header.h",
        "HEADER_SEARCH_PATHS": ["$(inherited)", "$(PROJECT_DIR)/Runner/PhoneMic"],
        "SWIFT_VERSION": "5.0", "ENABLE_BITCODE": "NO", "ENABLE_USER_SCRIPT_SANDBOXING": "NO",
        "BUILD_LIBRARY_FOR_DISTRIBUTION": "NO",
        "CLANG_ALLOW_NON_MODULAR_INCLUDES_IN_FRAMEWORK_MODULES": "YES",
        "TARGETED_DEVICE_FAMILY": "1", "LD_RUNPATH_SEARCH_PATHS": ["$(inherited)", "@executable_path/Frameworks"],
        "ASSETCATALOG_COMPILER_APPICON_NAME": "prodAppIcon",
        "SWIFT_ACTIVE_COMPILATION_CONDITIONS": "$(inherited) OMI_PHYSICAL_QUALIFICATION",
    }
    spec = {"name": "Runner", "options": {"deploymentTarget": {"iOS": "15.2"}},
            "configs": {"Debug": "debug", "Profile": "release", "Release": "release"}, "targets": {"Runner": {
                "type": "application", "platform": "iOS", "sources": sources,
                "configFiles": {"Profile": "Flutter/Profile.xcconfig"}, "settings": {"base": target_settings},
                "preBuildScripts": [{"name": "Flutter Build", "script": '/bin/sh "$FLUTTER_ROOT/packages/flutter_tools/bin/xcode_backend.sh" build', "basedOnDependencyAnalysis": False}],
                "postBuildScripts": [{"name": "Flutter Embed", "script": '/bin/sh "$FLUTTER_ROOT/packages/flutter_tools/bin/xcode_backend.sh" embed_and_thin', "basedOnDependencyAnalysis": False}],
            }}, "schemes": {"CaptureQualification": {"build": {"targets": {"Runner": "all"}}, "run": {"config": "Profile"}}}}
    spec_text = json.dumps(spec, indent=2)
    spec_path = ios / "project.json"
    unchanged_spec = spec_path.exists() and spec_path.read_text() == spec_text
    spec_path.write_text(spec_text)
    podfile = (app / "ios" / "Podfile").read_text()
    start, end = podfile.index("project 'Runner', {"), podfile.index("\n}\n", podfile.index("project 'Runner', {")) + 3
    podfile = podfile[:start] + "project 'Runner', {'Debug' => :debug, 'Profile' => :release, 'Release' => :release}\n" + podfile[end:]
    podfile = podfile.replace("require_relative 'rayban_dat_plugin_boundary'", "")
    start, end = podfile.index("if ENV['OMI_RAYBAN_DAT']"), podfile.index("\npost_install do")
    podfile = podfile[:start] + "target 'Runner' do\n  use_frameworks! :linkage => :static\n  use_modular_headers!\n  flutter_install_all_ios_pods File.dirname(File.realpath(__FILE__))\n  pod 'TwilioVoice', '~> 6.13'\nend\n" + podfile[end:]
    podfile_path = ios / "Podfile"
    unchanged_podfile = podfile_path.exists() and podfile_path.read_text() == podfile
    podfile_path.write_text(podfile)
    engine_cache = args.flutter_root / "bin/cache/artifacts/engine"
    if not all((engine_cache / mode / "Flutter.xcframework").exists()
               for mode in ("ios", "ios-profile", "ios-release")):
        run([str(args.flutter_root / "bin" / "flutter"), "precache", "--ios"], app, output / "flutter-precache.log")
    reuse_native_project = (
        unchanged_spec and unchanged_podfile
        and previous_plugins.get("plugins", {}).get("ios") == plugins["plugins"]["ios"]
        and f"FLUTTER_ROOT={args.flutter_root.resolve()}\n" in previous_flutter
        and (ios / "Runner.xcworkspace/contents.xcworkspacedata").exists()
        and (ios / "Pods/Manifest.lock").exists()
    )
    if not reuse_native_project:
        run(["xcodegen", "generate", "--spec", "project.json"], ios, output / "xcodegen.log")
        # Regeneration removes CocoaPods phases. Reintegrate whenever the
        # target/source/dependency graph changes, but preserve it for a Dart
        # scenario-only rebuild to avoid invalidating every native module.
        run(["pod", "install"], ios, output / "pod-install.log")
    receipt = {"app_source": str(app), "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=app, text=True).strip(),
               "bundle_id": args.bundle_id, "defines": defines, "excluded_plugins": sorted(EXCLUDED_PLUGINS),
               "scope": "Physical capture qualification; real Runner/BLE/phone mic; no extensions or shared entitlements",
               "source_sha256": {str(p.relative_to(runner)): hashlib.sha256(p.read_bytes()).hexdigest() for p in runner.rglob("*.swift")},
               "dart_input_sha256": input_hashes(app),
               "native_registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
               "native_registry_exclusions_verified": True,
               "built": False, "installed": False}
    if not args.prepare_only:
        run(["xcodebuild", "-workspace", "Runner.xcworkspace", "-scheme", "CaptureQualification", "-configuration", "Profile",
             "-destination", "generic/platform=iOS", "-derivedDataPath", str(output / "DerivedData"),
             "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", "CODE_SIGN_IDENTITY=", "build"], ios, output / "xcodebuild.log")
        product = output / "DerivedData/Build/Products/Profile-iphoneos/OmiCaptureQA.app"
        built_plist = plistlib.loads((product / "Info.plist").read_bytes())
        assert built_plist["CFBundleIdentifier"] == args.bundle_id
        assert built_plist["CFBundleDisplayName"] == "OmiCaptureQA"
        for key in ("FirebaseMessagingAutoInitEnabled", "FirebaseCrashlyticsCollectionEnabled", "FirebaseDataCollectionDefaultEnabled"):
            assert built_plist[key] is False, key
        assert not (product / "GoogleService-Info.plist").exists()
        assert not (product / "PlugIns").exists()
        compiled_storyboards = {}
        for name in ("Main", "LaunchScreen"):
            matches = [path for path in product.rglob(f"{name}.storyboardc")
                       if path.is_dir() and any(child.is_file() for child in path.rglob("*"))]
            assert len(matches) == 1, f"Missing or ambiguous compiled {name} storyboard: {matches}"
            compiled_storyboards[name] = str(matches[0].relative_to(product))
        scenes = built_plist["UIApplicationSceneManifest"]["UISceneConfigurations"]["UIWindowSceneSessionRoleApplication"]
        assert scenes[0]["UISceneStoryboardFile"] == "Main"
        # Xcode-managed wildcard development profiles cannot be selected using
        # Xcode's Manual mode. Sign the built diagnostic product explicitly;
        # never ask Xcode to create or fetch any provisioning resource.
        entitlements = {
            "application-identifier": args.team + "." + args.bundle_id,
            "com.apple.developer.team-identifier": args.team,
            "get-task-allow": profile["Entitlements"].get("get-task-allow", False),
            "keychain-access-groups": [args.team + "." + args.bundle_id],
        }
        entitlements_path = output / "CaptureQualification.entitlements"
        entitlements_path.write_bytes(plistlib.dumps(entitlements))
        shutil.copy(args.profile, product / "embedded.mobileprovision")
        nested = sorted((p for p in product.rglob("*") if p.suffix in (".framework", ".dylib")),
                        key=lambda p: len(p.parts), reverse=True)
        for index, path in enumerate(nested):
            run(["codesign", "--force", "--sign", args.identity, "--timestamp=none", str(path)],
                ios, output / f"codesign-nested-{index}.log")
        run(["codesign", "--force", "--sign", args.identity, "--timestamp=none", "--generate-entitlement-der",
             "--entitlements", str(entitlements_path), str(product)], ios, output / "codesign-app.log")
        run(["codesign", "--verify", "--deep", "--strict", str(product)], ios, output / "codesign-verify.log")
        if receipt["dart_input_sha256"] != input_hashes(app):
            raise RuntimeError("Dart build inputs changed during compilation; rebuild to bind receipt to source")
        product_files = hash_tree(product)
        receipt.update({"built": True, "product": str(product),
                        "compiled_storyboards_verified": compiled_storyboards,
                        "executable_sha256": hashlib.sha256((product / "OmiCaptureQA").read_bytes()).hexdigest(),
                        "signed_app_file_sha256": product_files,
                        "signed_app_tree_sha256": hashlib.sha256(json.dumps(product_files, sort_keys=True).encode()).hexdigest()})
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"receipt": str(output / "build-receipt.json"), "built": receipt["built"],
                      "product": receipt.get("product"), "signed_app_tree_sha256": receipt.get("signed_app_tree_sha256")}, indent=2))


if __name__ == "__main__":
    main()
