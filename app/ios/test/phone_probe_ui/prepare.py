#!/usr/bin/env python3
"""Generate an external Xcode UI-test project; never touches a device."""

import argparse
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    for name in ("Host.swift", "PermissionTests.swift"):
        shutil.copyfile(here / name, args.output / name)
    (args.output / "project.yml").write_text("""name: OmiProbePermissions
options:
  deploymentTarget:
    iOS: "16.0"
settings:
  base:
    SWIFT_VERSION: "5.0"
    CODE_SIGN_STYLE: Manual
    TARGETED_DEVICE_FAMILY: "1"
targets:
  ProbePermissionHost:
    type: application
    platform: iOS
    sources: [Host.swift]
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.friend-app-with-wearable.ios12.development.permissionhost
    info:
      path: Host-Info.plist
      properties:
        CFBundleDisplayName: Omi Permission Driver
        UILaunchScreen: {}
        UIApplicationSceneManifest:
          UIApplicationSupportsMultipleScenes: false
          UISceneConfigurations:
            UIWindowSceneSessionRoleApplication:
              - UISceneConfigurationName: Default
                UISceneDelegateClassName: $(PRODUCT_MODULE_NAME).SceneDelegate
  ProbePermissionTests:
    type: bundle.ui-testing
    platform: iOS
    sources: [PermissionTests.swift]
    dependencies:
      - target: ProbePermissionHost
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.friend-app-with-wearable.ios12.development.permissiontests
        GENERATE_INFOPLIST_FILE: YES
        TEST_TARGET_NAME: ProbePermissionHost
schemes:
  ProbePermissions:
    build:
      targets:
        ProbePermissionHost: all
        ProbePermissionTests: [test]
    test:
      targets: [ProbePermissionTests]
""")
    subprocess.run(
        ["xcodegen", "generate", "--spec", str(args.output / "project.yml"), "--project", str(args.output)], check=True
    )


if __name__ == "__main__":
    main()
