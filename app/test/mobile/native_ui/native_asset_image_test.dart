import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_asset_image.dart';

class _Temporary extends PathProviderPlatform {
  _Temporary(this.path);
  final String path;

  @override
  Future<String?> getTemporaryPath() async => path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final artwork = Uint8List.fromList(List.generate(64, (index) => index));
  final loads = <String>[];
  late Directory temporary;

  setUp(() async {
    temporary = await Directory.systemTemp.createTemp('omi-native-assets-test');
    final previous = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Temporary(temporary.path);
    loads.clear();
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMessageHandler('flutter/assets', (message) async {
      final key =
          Uri.decodeFull(utf8.decode(message!.buffer.asUint8List(message.offsetInBytes, message.lengthInBytes)));
      loads.add(key);
      return key.startsWith('assets/images/device_') ? ByteData.sublistView(artwork) : null;
    });
    addTearDown(() async {
      messenger.setMockMessageHandler('flutter/assets', null);
      PathProviderPlatform.instance = previous;
      await temporary.delete(recursive: true);
    });
  });

  test('only bundled artwork paths under assets/images are copied', () async {
    for (final path in [
      'assets/images/../device_secret.png',
      '/assets/images/device_front.png',
      'assets/images/device_front.PNG',
      'assets/images/device_front.gif',
      'assets/images/device_front',
      'assets/images//device_front.png',
      'assets/images/device front.png',
      'assets/images/device_front.png?raw',
      'assets/other/device_front.png',
      'file:///assets/images/device_front.png',
    ]) {
      expect(await nativeAssetImageUri(path), isNull, reason: path);
    }
    expect(loads, isEmpty, reason: 'A refused path never reaches the bundle');
  });

  test('a missing asset returns null, and its one memoized failure answers later requests', () async {
    expect(await nativeAssetImageUri('assets/images/missing_artwork.png'), isNull);
    expect(await nativeAssetImageUri('assets/images/missing_artwork.png'), isNull);
    expect(loads, ['assets/images/missing_artwork.png'], reason: 'The bundle is read once per process');
  });

  test('a copy that cannot be renamed into place returns null and leaves no partial file', () async {
    const asset = 'assets/images/device_back.png';
    // A directory already holds the target name, so the rename fails after the partial was written.
    final target = Directory('${temporary.path}/omi_native_assets/${sha1.convert(utf8.encode(asset))}.png');
    await target.create(recursive: true);
    await File('${target.path}/occupied').writeAsBytes([0]);
    expect(await nativeAssetImageUri(asset), isNull);
    expect(loads, [asset]);
    expect(File('${target.path}.partial').existsSync(), isFalse);
    expect(target.parent.listSync().map((entry) => entry.path), [target.path]);
  });

  test('the same asset returns the same file URI and is read and written once', () async {
    const asset = 'assets/images/device_front.webp';
    final first = nativeAssetImageUri(asset);
    expect(identical(nativeAssetImageUri(asset), first), isTrue, reason: 'Concurrent requests share one copy');
    final uri = await first;
    expect(uri, isNotNull);
    expect(nativeImageUri(uri), uri, reason: 'The native thumbnail accepts it as a sandbox file');
    final file = File.fromUri(Uri.parse(uri!));
    expect(file.path, '${temporary.path}/omi_native_assets/${sha1.convert(utf8.encode(asset))}.webp');
    expect(await file.readAsBytes(), artwork);
    expect(File('${file.path}.partial').existsSync(), isFalse);

    // A later request reuses the copy: the bundle is not read again and the file is not rewritten.
    await file.writeAsBytes([1, 2, 3]);
    expect(await nativeAssetImageUri(asset), uri);
    expect(await file.readAsBytes(), [1, 2, 3]);
    expect(loads, [asset]);
  });
}
