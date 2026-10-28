import 'dart:io';
import 'dart:typed_data';

/// Loads an SF Pro Display OTF fixture for render tests.
///
/// The OTFs under `test/fonts/` are fixtures only and are deliberately not
/// declared in `pubspec.yaml`: bundling SF Pro in an IPA is disallowed by
/// Apple's font license (ITMS-91182), so they must never re-enter the asset
/// bundle. Tests read them from the package tree instead of `rootBundle`.
Future<ByteData> sfProFont(String file) async {
  var font = File('app/test/fonts/$file');
  if (!font.existsSync()) font = File('test/fonts/$file');
  return ByteData.sublistView(Uint8List.fromList(font.readAsBytesSync()));
}
