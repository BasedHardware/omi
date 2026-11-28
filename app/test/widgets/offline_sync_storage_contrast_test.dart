import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/offline_sync_storage_sheet.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/ui/ui.dart';

const _empty = StorageAmounts(
  uploadedSeconds: 0,
  uploadedCount: 0,
  phonePendingSeconds: 0,
  devicePendingSeconds: 0,
  pendingCount: 0,
  allCount: 0,
  allSeconds: 0,
);

// Shaped like the report that prompted the copy: tens of thousands of ~1 min
// files read as conversations, with audio waiting both on the phone and the pendant.
const _busy = StorageAmounts(
  uploadedSeconds: 440 * 3600,
  uploadedCount: 26589,
  phonePendingSeconds: 71 * 3600,
  devicePendingSeconds: 11 * 3600,
  pendingCount: 4937,
  allCount: 31526,
  allSeconds: 522 * 3600,
);

double contrast(Color foreground, Color background) {
  final opaque = Color.alphaBlend(foreground, background);
  final a = opaque.computeLuminance();
  final b = background.computeLuminance();
  return (math.max(a, b) + .05) / (math.min(a, b) + .05);
}

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('Offline Sync storage labels are readable in $brightness', (tester) async {
      final previous = OmiColors.active;
      OmiColors.active = OmiColors.forBrightness(brightness);
      addTearDown(() => OmiColors.active = previous);
      await tester.pumpWidget(MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: OfflineSyncStorageSheet(
          amounts: _empty,
          onFreeUpSpace: () => fail('nothing uploaded must not offer freeing space'),
          onDeletePending: () => fail('nothing pending must not offer deleting'),
          onDeleteAll: () => fail('nothing stored must not offer deleting'),
        )),
      ));
      await tester.pumpAndSettle();
      for (final label in [
        'Already uploaded',
        'Not uploaded yet',
        'Transcribed. Removing the phone copy loses nothing.'
      ]) {
        final text = find.text(label);
        expect(text, findsOneWidget);
        final cards = tester
            .widgetList<Container>(find.ancestor(of: text, matching: find.byType(Container)))
            .where((w) => w.decoration is BoxDecoration && (w.decoration! as BoxDecoration).color != null);
        final background = (cards.first.decoration! as BoxDecoration).color!;
        final foreground = tester.widget<Text>(text).style!.color!;
        expect(contrast(foreground, background), greaterThanOrEqualTo(4.5), reason: '$label in $brightness');
      }
      final count = find.text('0s');
      expect(count, findsNWidgets(2));
      for (final element in count.evaluate()) {
        final text = element.widget as Text;
        final badge = element.findAncestorWidgetOfExactType<Container>()!;
        final fill = (badge.decoration! as BoxDecoration).color!;
        final background = Color.alphaBlend(fill, OmiColors.surface2);
        expect(contrast(text.style!.color!, background), greaterThanOrEqualTo(4.5));
      }
      expect(find.text('Free up space'), findsNothing);
      expect(find.text('Delete'), findsNothing);
      expect(find.text('Delete everything'), findsNothing);
      expect(tester.takeException(), isNull);
    });
    testWidgets('clear actions remain readable and reachable on a narrow French sheet in $brightness', (tester) async {
      final previous = OmiColors.active;
      OmiColors.active = OmiColors.forBrightness(brightness);
      addTearDown(() => OmiColors.active = previous);
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(MaterialApp(
        locale: const Locale('fr'),
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(2)),
          child: child!,
        ),
        home: Scaffold(
            body: SingleChildScrollView(
                child: Padding(
          padding: const EdgeInsets.all(OmiSpacing.xl),
          child: OfflineSyncStorageSheet(
            amounts: _busy,
            onFreeUpSpace: () {},
            onDeletePending: () {},
            onDeleteAll: () {},
          ),
        ))),
      ));
      await tester.pumpAndSettle();
      final context = tester.element(find.byType(OfflineSyncStorageSheet));
      final l10n = AppLocalizations.of(context);
      expect(find.text(l10n.storageUploadedTitle), findsOneWidget);
      expect(find.text(l10n.storageNotUploadedTitle), findsOneWidget);
      for (final label in [l10n.storageFreeUpSpace, l10n.delete]) {
        final element = find.text(label).evaluate().single;
        final text = element.widget as Text;
        final finder = find.ancestor(of: find.byWidget(text), matching: find.byType(OmiButton)).first;
        await tester.ensureVisible(finder);
        await tester.pumpAndSettle();
        final bounds = tester.getRect(finder);
        expect(bounds.width, greaterThanOrEqualTo(kOmiMinTapTarget));
        expect(bounds.height, greaterThanOrEqualTo(kOmiMinTapTarget));
        expect(finder.hitTestable(), findsOneWidget);
      }
      expect(tester.takeException(), isNull);
    });

    testWidgets('Home empty state stays visible in $brightness', (tester) async {
      final previous = OmiColors.active;
      OmiColors.active = OmiColors.forBrightness(brightness);
      addTearDown(() => OmiColors.active = previous);
      await tester.pumpWidget(MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: const Scaffold(body: Center(child: NoConversationsHero())),
      ));
      await tester.pumpAndSettle();
      final title = find.text('No conversations yet');
      expect(title.hitTestable(), findsOneWidget);
      expect(contrast(tester.widget<Text>(title).style!.color!, OmiColors.surface0), greaterThanOrEqualTo(4.5));
      expect(find.byIcon(Icons.forum_rounded), findsOneWidget);
    });
  }
  testWidgets('rows read as hours of audio and where it waits, never as file counts', (tester) async {
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(
          body: OfflineSyncStorageSheet(
        amounts: _busy,
        onFreeUpSpace: () => calls.add('uploaded'),
        onDeletePending: () => calls.add('notUploaded'),
        onDeleteAll: () => calls.add('all'),
      )),
    ));
    await tester.pumpAndSettle();
    expect(find.text('440h'), findsOneWidget);
    expect(find.text('82h'), findsOneWidget);
    expect(find.text('On this phone 71h · On your Omi 11h'), findsOneWidget);
    expect(find.text('Deleting loses this audio for good.'), findsOneWidget);
    expect(find.text('26589'), findsNothing);
    expect(find.text('4937'), findsNothing);
    await tester.tap(find.text('Free up space'));
    await tester.tap(find.text('Delete'));
    await tester.tap(find.text('Delete everything'));
    expect(calls, ['uploaded', 'notUploaded', 'all']);
  });

  testWidgets('pending audio only on the phone or only on the pendant names that place alone', (tester) async {
    for (final (amounts, where) in [
      (
        const StorageAmounts(
            uploadedSeconds: 0,
            uploadedCount: 0,
            phonePendingSeconds: 600,
            devicePendingSeconds: 0,
            pendingCount: 10,
            allCount: 10,
            allSeconds: 600),
        'On this phone'
      ),
      (
        const StorageAmounts(
            uploadedSeconds: 0,
            uploadedCount: 0,
            phonePendingSeconds: 0,
            devicePendingSeconds: 11 * 3600,
            pendingCount: 1,
            allCount: 1,
            allSeconds: 11 * 3600),
        'On your Omi'
      ),
    ]) {
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: OfflineSyncStorageSheet(
                amounts: amounts, onFreeUpSpace: () {}, onDeletePending: () {}, onDeleteAll: () {})),
      ));
      await tester.pumpAndSettle();
      expect(find.text(where), findsOneWidget);
      expect(find.text('Free up space'), findsNothing, reason: 'nothing uploaded to free');
    }
  });
}
