import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/screen_frames.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_screenshots_section.dart';
import 'package:omi/widgets/media_viewer_page.dart';

final _t0 = DateTime.utc(2026, 9, 30, 12);

ConversationScreenshot _frame(String id, {String caption = '', bool banner = false, DateTime? expires}) =>
    ConversationScreenshot(
      id: id,
      capturedAt: _t0,
      isBanner: banner,
      caption: caption,
      width: 1600,
      height: 1000,
      contentUrl: 'https://storage.test/$id.jpg',
      thumbnailUrl: 'https://storage.test/$id-thumb.jpg',
      urlExpiresAt: expires ?? _t0.add(const Duration(minutes: 60)),
    );

ConversationScreenshots _set(List<ConversationScreenshot> frames, {int revision = 1}) =>
    ConversationScreenshots(revision: revision, frames: frames);

class _Fake {
  _Fake(this.responses);

  /// Served in order; the last one repeats.
  final List<ApiResult<ConversationScreenshots>> responses;
  int fetches = 0;
  final deleted = <String>[];
  ApiResult<ConversationScreenshots> deleteResponse = const ApiSuccess(ConversationScreenshots.empty);

  Future<ApiResult<ConversationScreenshots>> fetch(String conversationId) async {
    expect(conversationId, 'conv-1');
    final r = responses[fetches < responses.length ? fetches : responses.length - 1];
    fetches++;
    return r;
  }

  Future<ApiResult<ConversationScreenshots>> delete(String conversationId, String frameId) async {
    deleted.add(frameId);
    return deleteResponse;
  }
}

Future<void> _pump(WidgetTester tester, _Fake fake, {DateTime Function()? now}) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: Scaffold(
      body: CustomScrollView(slivers: [
        ConversationScreenshotsSection(
          conversationId: 'conv-1',
          fetch: fake.fetch,
          delete: fake.delete,
          loadBytes: (_) async => base64Decode(
              'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='),
          now: now ?? () => _t0,
        ),
      ]),
    ),
  ));
  await tester.pump();
  await tester.pump();
}

Finder get _section => find.byKey(const ValueKey('conversation_screenshots_section'));
Finder _tile(String id) => find.byKey(ValueKey('conversation_screenshot_$id'));

void main() {
  testWidgets('an empty set renders nothing at all', (tester) async {
    final fake = _Fake([const ApiSuccess(ConversationScreenshots.empty)]);
    await _pump(tester, fake);
    expect(fake.fetches, 1);
    expect(_section, findsNothing);
    expect(find.text('What was on screen'), findsNothing);
  });

  testWidgets('a fetch that throws renders nothing and does not fail the page', (tester) async {
    final fake = _Fake([const ApiSuccess(ConversationScreenshots.empty)]);
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(
        body: CustomScrollView(slivers: [
          ConversationScreenshotsSection(conversationId: 'conv-1', fetch: (_) => throw StateError('boom')),
        ]),
      ),
    ));
    await tester.pump();
    expect(fake.fetches, 0);
    expect(_section, findsNothing);
  });

  testWidgets('a failed fetch renders nothing — never an error card', (tester) async {
    final fake = _Fake([const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 503))]);
    await _pump(tester, fake);
    expect(_section, findsNothing);
    expect(find.textContaining('wrong'), findsNothing);
  });

  testWidgets('banner leads the strip; captions shown, empty caption falls back', (tester) async {
    final fake = _Fake([
      ApiSuccess(_set([
        _frame('b', caption: 'Weekly sync on Meet', banner: true),
        _frame('s1', caption: 'Roadmap slide'),
        _frame('s2'),
      ])),
    ]);
    await _pump(tester, fake);
    expect(_section, findsOneWidget);
    expect(find.text('What was on screen'), findsOneWidget);
    expect(find.text('Weekly sync on Meet'), findsOneWidget);
    expect(find.text('Roadmap slide'), findsOneWidget);
    expect(find.text('Screenshot from this meeting'), findsOneWidget);
    final bx = tester.getTopLeft(_tile('b')).dx;
    final s1x = tester.getTopLeft(_tile('s1')).dx;
    expect(bx, lessThan(s1x));
  });

  test('decoding the set puts the banner first and never repeats it', () async {
    Env.overrideApiBaseUrl('http://127.0.0.1:9/');
    addTearDown(Env.clearApiBaseUrlOverrideForTesting);
    final frame = {
      'captured_at': '2026-09-30T12:00:00Z',
      'rank': 0,
      'caption': 'c',
      'labels': <String>[],
      'width': 10,
      'height': 10,
      'content_url': 'u',
      'thumbnail_url': 't',
      'url_expires_at': '2026-09-30T13:00:00Z',
      'ground': {
        'stops': ['#000000', '#FFFFFF'],
        'is_neutral': true
      },
    };
    final result = await getConversationScreenshots('conv-1',
        send: (request) async => http.Response(
            jsonEncode({
              'revision': 3,
              'banner': {...frame, 'id': 'b', 'role': 'banner'},
              'strip': [
                {...frame, 'id': 's1', 'role': 'strip'},
                {...frame, 'id': 'b', 'role': 'banner'},
              ],
            }),
            200));
    final set = (result as ApiSuccess<ConversationScreenshots>).data;
    expect(set.frames.map((f) => f.id), ['b', 's1']);
    expect(set.frames.first.isBanner, isTrue);
    expect(set.urlsExpireAt!.isAtSameMomentAs(DateTime.utc(2026, 9, 30, 13)), isTrue);
  });

  testWidgets('tap opens the viewer on the whole set at the tapped frame', (tester) async {
    final fake = _Fake([
      ApiSuccess(_set([_frame('b', banner: true), _frame('s1'), _frame('s2')]))
    ]);
    await _pump(tester, fake);
    await tester.tap(_tile('s1'));
    await tester.pumpAndSettle();
    final viewer = tester.widget<MediaViewerPage>(find.byType(MediaViewerPage));
    expect(viewer.items, hasLength(3));
    expect(viewer.initialIndex, 1);
    expect(viewer.items.every((i) => i.bytesLoader != null && i.showCaptionStrip && i.caption != null), isTrue);
    expect(fake.fetches, 1, reason: 'fresh URLs are not re-fetched');
  });

  testWidgets('an expired set is re-fetched before the viewer opens', (tester) async {
    var now = _t0;
    final fake = _Fake([
      ApiSuccess(_set([_frame('a'), _frame('b')])),
      ApiSuccess(_set([_frame('b', expires: _t0.add(const Duration(minutes: 120)))], revision: 2)),
    ]);
    await _pump(tester, fake, now: () => now);
    now = _t0.add(const Duration(minutes: 59));
    await tester.tap(_tile('b'));
    await tester.pumpAndSettle();
    expect(fake.fetches, 2);
    final viewer = tester.widget<MediaViewerPage>(find.byType(MediaViewerPage));
    expect(viewer.items, hasLength(1), reason: 'the viewer gets the refreshed set, not the stale one');
    expect(viewer.initialIndex, 0);
  });

  testWidgets('the set is re-fetched shortly before its URLs expire while the note stays open', (tester) async {
    final fake = _Fake([
      ApiSuccess(_set([_frame('a')])),
    ]);
    await _pump(tester, fake);
    expect(fake.fetches, 1);
    await tester.pump(const Duration(minutes: 57));
    expect(fake.fetches, 1);
    await tester.pump(const Duration(minutes: 1, seconds: 1));
    expect(fake.fetches, 2);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a set that arrives already expired does not loop on its own timer', (tester) async {
    final fake = _Fake([
      ApiSuccess(_set([_frame('a', expires: _t0)])),
    ]);
    await _pump(tester, fake);
    await tester.pump(const Duration(minutes: 90));
    // The test HTTP client fails every thumbnail; neither those failures nor the timer re-fetch
    // a set that was already stale when it arrived.
    expect(fake.fetches, 1);
  });

  testWidgets('long-press → Delete → confirm deletes the frame and adopts the server set', (tester) async {
    final fake = _Fake([
      ApiSuccess(_set([_frame('b', banner: true, caption: 'Banner'), _frame('s1', caption: 'Other')]))
    ]);
    fake.deleteResponse = ApiSuccess(_set([_frame('s1', caption: 'Other', banner: true)], revision: 2));
    await _pump(tester, fake);

    await tester.longPress(_tile('b'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(find.text('Delete Screenshot?'), findsOneWidget);
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();

    expect(fake.deleted, ['b']);
    expect(_tile('b'), findsNothing);
    expect(_tile('s1'), findsOneWidget);
  });

  testWidgets('cancelling the confirmation deletes nothing', (tester) async {
    final fake = _Fake([
      ApiSuccess(_set([_frame('b', caption: 'Banner')]))
    ]);
    await _pump(tester, fake);
    await tester.longPress(_tile('b'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(fake.deleted, isEmpty);
    expect(_tile('b'), findsOneWidget);
  });

  testWidgets('deleting the last frame hides the section', (tester) async {
    final fake = _Fake([
      ApiSuccess(_set([_frame('only', caption: 'Only one')]))
    ]);
    await _pump(tester, fake);
    await tester.longPress(_tile('only'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(fake.deleted, ['only']);
    expect(_section, findsNothing);
  });
}
