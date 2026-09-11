import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/widgets/omi_map_preview.dart';
import 'package:omi/pages/conversations/conversation_map_page.dart';

class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
}

void main() {
  // The page preview builds proxy URLs from Env.apiBaseUrl (per-isolate statics).
  setUpAll(() => Env.init(_TestEnvFields()));

  test('omits missing and invalid locations without failing the map', () {
    final groups = buildConversationMapGroups([
      _conversation('missing'),
      _conversation('invalid', latitude: 91, longitude: 0),
      _conversation('valid', latitude: 37.7749, longitude: -122.4194),
    ]);

    expect(groups, hasLength(1));
    expect(groups.single.conversations.single.id, 'valid');
  });

  test('clusters dense repeated locations into one selectable marker', () {
    final groups = buildConversationMapGroups([
      _conversation('first', latitude: 37.77491, longitude: -122.41941),
      _conversation('second', latitude: 37.77494, longitude: -122.41944),
    ]);

    expect(groups, hasLength(1));
    expect(groups.single.conversations.map((conversation) => conversation.id), ['first', 'second']);
    expect(groups.single.membershipKey, 'first%2Csecond');
  });

  test('clusters points across a rounded-coordinate boundary', () {
    final groups = buildConversationMapGroups([
      _conversation('first', latitude: 0, longitude: 0.00049),
      _conversation('second', latitude: 0, longitude: 0.00051),
    ]);

    expect(groups, hasLength(1));
    expect(groups.single.conversations.map((conversation) => conversation.id), ['first', 'second']);
  });

  test('does not merge a transitive chain beyond the cluster radius', () {
    final groups = buildConversationMapGroups([
      _conversation('a', latitude: 0, longitude: 0),
      _conversation('b', latitude: 0, longitude: 0.0005),
      _conversation('c', latitude: 0, longitude: 0.001),
    ]);

    expect(groups, hasLength(2));
    expect(groups[0].conversations.map((conversation) => conversation.id), ['a', 'b']);
    expect(groups[1].conversations.map((conversation) => conversation.id), ['c']);
  });

  test('honors the supplied conversation set, including discarded items', () {
    final groups = buildConversationMapGroups([
      _conversation('discarded', latitude: 37.7749, longitude: -122.4194, discarded: true),
    ]);

    expect(groups, hasLength(1));
    expect(groups.single.conversations.single.id, 'discarded');
  });

  test('cluster membership key is stable across provider ordering', () {
    final first = buildConversationMapGroups([
      _conversation('second', latitude: 37.77494, longitude: -122.41944),
      _conversation('first', latitude: 37.77491, longitude: -122.41941),
    ]).single.membershipKey;
    final second = buildConversationMapGroups([
      _conversation('first', latitude: 37.77491, longitude: -122.41941),
      _conversation('second', latitude: 37.77494, longitude: -122.41944),
    ]).single.membershipKey;

    expect(first, second);
  });

  testWidgets('empty map remains usable when the filtered view has no locations', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ConversationMapPage(conversations: []),
      ),
    );

    expect(find.text('Conversations · Location'), findsOneWidget);
    expect(find.text('No conversations yet'), findsOneWidget);
  });

  testWidgets('distinguishes conversations with no usable location', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ConversationMapPage(conversations: [_conversation('unknown')]),
      ),
    );

    expect(find.text('Unknown location'), findsOneWidget);
    expect(find.text('No conversations yet'), findsNothing);
  });

  testWidgets('preview and grouped rows expose stable descriptive keys', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ConversationMapPage(
          conversations: [
            _conversation('first', latitude: 37.77491, longitude: -122.41941),
            _conversation('second', latitude: 37.77494, longitude: -122.41944),
          ],
        ),
      ),
    );
    await tester.pump();

    // One static preview over every cluster anchor, one row per place.
    expect(find.byKey(const ValueKey('conversation_map_preview')), findsOneWidget);
    expect(find.byType(OmiMapPreview), findsOneWidget);
    final group = find.byKey(const ValueKey('conversation_map_marker_first%2Csecond'));
    expect(group, findsOneWidget);

    await tester.tap(group);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('conversation_map_cluster_row_first')), findsOneWidget);
    expect(find.byKey(const ValueKey('conversation_map_cluster_row_second')), findsOneWidget);
  });
}

ServerConversation _conversation(String id, {double? latitude, double? longitude, bool discarded = false}) =>
    ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 8, 1),
      structured: Structured('Title', 'Overview'),
      discarded: discarded,
      geolocation: latitude == null || longitude == null ? null : Geolocation(latitude: latitude, longitude: longitude),
    );
