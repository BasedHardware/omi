import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';
import 'package:visibility_detector/visibility_detector.dart';
import '../support/custody_test_helpers.dart';
import '../support/typed_conversation_screen.dart';

class _EnvFields implements EnvFields {
  const _EnvFields();
  @override
  String get apiBaseUrl => '';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(rootBundle.load('assets/fonts/SFPRODISPLAY$weight.OTF'));
    }
    await loader.load();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(const _EnvFields());
    await _loadFonts();
  });
  for (final processing in [false, true]) {
    testWidgets('Home renders only explicit Transcribe Later rows (processing=$processing)', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393, 852);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      VisibilityDetectorController.instance.updateInterval = Duration.zero;
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      final boundary = GlobalKey();
      late Directory dir;
      late LocalRecordingsProvider view;
      await tester.runAsync(() async {
        dir = await custodyDirectory();
        final timestamp = DateTime.now().subtract(const Duration(minutes: 20)).millisecondsSinceEpoch ~/ 1000;
        for (final marker in ['omibatchphone', 'omibatchphoneauto', 'omibatchlimitless']) {
          await File('${dir.path}/audio_${marker}_opus_16000_1_fs320_$timestamp.bin').writeAsBytes([1, 0, 0, 0, 5]);
        }
        // Twelve Watch minute copies with receipts: none becomes a Home row.
        const session = '0123456789abcdef0123456789abcdef';
        await Directory('${dir.path}/.watch-receipts').create();
        for (var i = 0; i < 12; i++) {
          final start = timestamp + i * 60;
          final name = 'audio_omibatchwatch${session}s${i}_pcm16_16000_1_fs160_$start.bin';
          await File('${dir.path}/$name').writeAsBytes([1, 0, 0, 0, 5]);
          await File('${dir.path}/.watch-receipts/$name').writeAsString(jsonEncode({
            'metadata': {'version': 1, 'sessionID': session, 'segment': i, 'startedAt': start, 'ownerUID': 'owner'},
            'digest': 'a' * 64
          }));
        }
        final ledger = await custodyLedger();
        await NativeRecordingIntake(ledger, dedupeOff: () async => true).scan();
        if (processing) {
          final manual = (await ledger.getAllWals()).singleWhere((w) => w.holdForUser);
          manual.status = WalStatus.uploaded;
          manual.jobId = 'synthetic-processing-job';
          await ledger.persistRetryMetadata(manual);
        }
        view = LocalRecordingsProvider(ledger: ledger, initialize: false);
        await view.refresh();
        expect((await ledger.getAllWals()).length, 15);
        expect(view.recordings.length, 1);
      });
      addTearDown(() async {
        view.dispose();
        await dir.delete(recursive: true);
      });
      final items = [
        ServerConversation(
            id: 'synthetic',
            createdAt: DateTime.now(),
            structured: Structured('Planning the weekend', 'Synthetic conversation', emoji: '', category: 'personal'),
            status: ConversationStatus.completed)
      ];
      final conversations =
          ConversationProvider(conversationListFetcher: () async => (items: items, ok: true), isSignedIn: () => true)
            ..conversations = items
            ..groupConversationsByDate();
      addTearDown(conversations.dispose);
      final screen = await buildTypedConversationScreen(conversations,
          recordingsProvider: view, initializePreferences: false, theme: buildOmiTheme(brightness: Brightness.dark));
      await tester.pumpWidget(RepaintBoundary(key: boundary, child: screen));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(find.byType(RecordingListItem), findsOneWidget);
      expect(find.text('Planning the weekend'), findsOneWidget);
      if (processing) expect(find.text('Uploaded · processing on Omi'), findsOneWidget);
      expect(tester.takeException(), isNull);
      const output = String.fromEnvironment('CUSTODY_RENDER_OUTPUT');
      if (output.isNotEmpty) {
        await tester.runAsync(() async {
          final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final image = await render.toImage(pixelRatio: 3);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          await Directory(output).create(recursive: true);
          final file =
              processing ? '002-mobile-ios-phone-custody-processing.png' : '001-mobile-ios-phone-custody-home.png';
          await File('$output/$file').writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
