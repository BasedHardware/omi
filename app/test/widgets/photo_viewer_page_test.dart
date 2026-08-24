import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/widgets/conversation_photo_image.dart';

const _onePixelPng = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';

ConversationPhoto _photo({String base64 = '', String? storageId = 'storage-1'}) {
  return ConversationPhoto(
    id: 'photo-1',
    base64: base64,
    storageId: storageId,
    createdAt: DateTime.utc(2026, 8, 24),
  );
}

Widget _localized(Widget child) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('inline base64 photo renders without calling storage', (tester) async {
    var storageCalls = 0;
    final cache = ConversationPhotoBytesCache(
      fetchStorageImage: (_, __) async {
        storageCalls++;
        return Uint8List.fromList(base64Decode(_onePixelPng));
      },
    );

    await tester.pumpWidget(
      _localized(
        ConversationPhotoImage(
          photo: _photo(base64: _onePixelPng, storageId: null),
          conversationId: 'conversation-1',
          cache: cache,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(storageCalls, 0);
    expect(find.byType(Image), findsOneWidget);
  });

  testWidgets('storage-backed success renders returned bytes', (tester) async {
    final expectedBytes = Uint8List.fromList(base64Decode(_onePixelPng));
    var requestedConversationId = '';
    var requestedPhotoId = '';
    final cache = ConversationPhotoBytesCache(
      fetchStorageImage: (conversationId, photoId) async {
        requestedConversationId = conversationId;
        requestedPhotoId = photoId;
        return expectedBytes;
      },
    );

    await tester.pumpWidget(
      _localized(
        ConversationPhotoImage(photo: _photo(), conversationId: 'conversation-1', cache: cache),
      ),
    );
    await tester.pumpAndSettle();

    expect(requestedConversationId, 'conversation-1');
    expect(requestedPhotoId, 'photo-1');
    expect(find.byType(Image), findsOneWidget);
    expect(find.text('File unavailable'), findsNothing);
  });

  testWidgets('completed missing or offline photo is terminal and accessible', (tester) async {
    for (final fetch in <Future<Uint8List?> Function(String, String)>[
      (_, __) async => null,
      (_, __) async => throw StateError('offline'),
    ]) {
      final cache = ConversationPhotoBytesCache(fetchStorageImage: fetch);
      await tester.pumpWidget(
          _localized(ConversationPhotoImage(photo: _photo(), conversationId: 'conversation-1', cache: cache)));
      await tester.pumpAndSettle();

      expect(find.byType(CircularProgressIndicator), findsNothing);
      expect(find.text('File unavailable'), findsOneWidget);
      expect(tester.getSemantics(find.text('File unavailable')).label, 'File unavailable');
    }
  });

  testWidgets('rebuilding the image widget reuses one storage request', (tester) async {
    var storageCalls = 0;
    final cache = ConversationPhotoBytesCache(
      fetchStorageImage: (_, __) async {
        storageCalls++;
        return Uint8List.fromList(base64Decode(_onePixelPng));
      },
    );

    Widget buildImage() => _localized(
          ConversationPhotoImage(
            photo: _photo(),
            conversationId: 'conversation-1',
            cache: cache,
          ),
        );

    await tester.pumpWidget(buildImage());
    await tester.pumpAndSettle();
    await tester.pumpWidget(buildImage());
    await tester.pumpAndSettle();

    expect(storageCalls, 1);
  });
}
