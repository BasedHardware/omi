#!/usr/bin/env python3
"""Verify the built heavy APK cannot eagerly initialize native Firebase."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ANDROID = '{http://schemas.android.com/apk/res/android}'


def validate(xml):
    manifest = ET.fromstring(xml)
    if manifest.get('package') != 'com.friend.ios.dev':
        raise ValueError('heavy APK must use the DEV package')
    providers = [node.get(ANDROID + 'name', '') for node in manifest.findall('./application/provider')]
    if 'com.google.firebase.provider.FirebaseInitProvider' in providers:
        raise ValueError('native Firebase initializer remains in the heavy APK')
    return {'package': manifest.get('package'), 'firebase_auto_initializer_absent': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    analyzer = shutil.which('apkanalyzer')
    if analyzer is None:
        adb = shutil.which('adb')
        if adb:
            analyzer = str(Path(adb).resolve().parents[1] / 'cmdline-tools/latest/bin/apkanalyzer')
    try:
        if analyzer is None:
            raise ValueError('apkanalyzer from the Android SDK is required')
        xml = subprocess.run([analyzer, 'manifest', 'print', str(args.apk)], check=True,
                             capture_output=True, text=True, timeout=60).stdout
        args.out.write_text(json.dumps(validate(xml), indent=2) + '\n')
    except (ValueError, OSError, ET.ParseError, subprocess.SubprocessError) as error:
        parser.exit(65, f'heavy APK admission refused: {error}\n')


if __name__ == '__main__':
    main()
