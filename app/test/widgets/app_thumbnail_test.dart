import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/apps/widgets/app_thumbnail.dart';

class _UnavailableImageCache extends Fake implements BaseCacheManager {
  final response = StreamController<FileResponse>();

  @override
  Stream<FileResponse> getFileStream(String url,
          {String? key, Map<String, String>? headers, bool withProgress = false}) =>
      response.stream;
}

void main() {
  testWidgets('a missing thumbnail keeps its space and shows an image placeholder, not an app error', (tester) async {
    final cache = _UnavailableImageCache();
    final original = CachedNetworkImageProvider.defaultCacheManager;
    CachedNetworkImageProvider.defaultCacheManager = cache;
    addTearDown(() async {
      CachedNetworkImageProvider.defaultCacheManager = original;
      await cache.response.close();
      PaintingBinding.instance.imageCache.clear();
      PaintingBinding.instance.imageCache.clearLiveImages();
    });
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: Center(child: AppThumbnail(imageUrl: 'https://example.invalid/missing.png'))),
    ));
    final thumbnail = find.byType(AppThumbnail);
    expect(tester.getSize(thumbnail), const Size(60, 60));
    expect(find.byIcon(Icons.image_not_supported_outlined), findsNothing);
    // Drive the actual image stream from loading to failure without networking,
    // disk caches, plugins, timers or a replacement presentation widget.
    cache.response.addError(StateError('thumbnail unavailable'));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.image_not_supported_outlined), findsOneWidget);
    expect(find.byIcon(Icons.error_outline), findsNothing);
    expect(tester.getSize(thumbnail), const Size(60, 60));
    expect(tester.takeException(), isNull);
  });
}
