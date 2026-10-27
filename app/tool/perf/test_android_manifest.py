import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('android_manifest', Path(__file__).with_name('android_manifest.py'))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class AndroidManifestTests(unittest.TestCase):
    def manifest(self, package='com.friend.ios.dev', provider=''):
        return (f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{package}">'
                f'<application>{provider}</application></manifest>')

    def test_real_eager_initializer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'initializer remains'):
            guard.validate(self.manifest(provider='<provider android:name="com.google.firebase.provider.FirebaseInitProvider"/>'))

    def test_non_dev_apk_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'DEV package'):
            guard.validate(self.manifest(package='com.friend.ios'))

    def test_unrelated_providers_remain_allowed(self):
        receipt = guard.validate(self.manifest(provider='<provider android:name="androidx.startup.InitializationProvider"/>'))
        self.assertTrue(receipt['firebase_auto_initializer_absent'])


if __name__ == '__main__':
    unittest.main()
