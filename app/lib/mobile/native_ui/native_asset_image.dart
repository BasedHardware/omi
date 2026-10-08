import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import 'ios_native_surface.dart';

final _bundledImage = RegExp(r'^assets/images/[A-Za-z0-9_/-]+\.(png|jpg|jpeg|webp)$');
final _copies = <String, Future<String?>>{};

/// A file URI for bundled artwork that native thumbnails and image rows can read, or null on any
/// failure. Only static app assets under assets/images/ cross, never user data, so the copies in
/// `omi_native_assets` need no session cleanup. Each asset is read and written once per process: its
/// one memoized answer, a failure included, serves every later request.
Future<String?> nativeAssetImageUri(String asset) {
  if (!_bundledImage.hasMatch(asset) || asset.contains('..') || asset.split('/').contains('')) {
    return Future.value(null);
  }
  return _copies.putIfAbsent(asset, () => _copy(asset));
}

Future<String?> _copy(String asset) async {
  File? partial;
  try {
    final data = await rootBundle.load(asset);
    final directory = Directory('${(await getTemporaryDirectory()).path}/omi_native_assets');
    await directory.create(recursive: true);
    final extension = asset.substring(asset.lastIndexOf('.') + 1);
    final file = File('${directory.path}/${sha1.convert(utf8.encode(asset))}.$extension');
    // Write beside the target and rename, so a reader never sees a partial image.
    partial = File('${file.path}.partial');
    await partial.writeAsBytes(data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes), flush: true);
    await partial.rename(file.path);
    return nativeImageUri(Uri.file(file.path).toString());
  } catch (_) {
    // A failed write or rename (a full disk, say) leaves no partial image behind.
    try {
      if (await partial?.exists() == true) await partial!.delete();
    } catch (_) {
      /* Best effort: the system purges its temporary directory. */
    }
    return null;
  }
}
