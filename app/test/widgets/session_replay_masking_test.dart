import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
// ignore: implementation_imports
import 'package:posthog_flutter/src/replay/mask/posthog_mask_controller.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/chat_composer_parts.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Session replay masks Text, TextField and Image render objects by itself. Anything painted another
// way (a canvas, a decoration image) reaches replay frames unless a PostHogMaskWidget leaf covers it.
// These pin the surfaces that show the user's own content that way.

final _photo = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEUlEQVR4nGM4UaGBFTEMLQkAUtVaAV8W4QQAAAAASUVORK5CYII=');

Widget _app(Widget home) => PostHogWidget(
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: home,
      ),
    );

/// True when one of the rects the SDK paints black in a replay frame covers [target].
bool _masked(Rect target) {
  final elements = PostHogMaskController.instance.getCurrentWidgetsElements() ?? const [];
  return elements.any((element) {
    final transform = element.transform;
    final rect = (transform == null ? element.rect : MatrixUtils.transformRect(transform, element.rect)).inflate(0.5);
    return rect.contains(target.topLeft) && rect.contains(target.bottomRight);
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('the Mind Map canvas, which paints names and relations, is masked', (tester) async {
    await tester.pumpWidget(_app(MemoryGraphPage(
      trackOpenEvent: false,
      loadGraph: () async => {
        'nodes': [
          {'id': 'user', 'label': 'user', 'node_type': 'person'},
          {'id': 'ent_1611f3f21a8027b7c4f5', 'label': 'Sam Altman', 'node_type': 'person'},
        ],
        'edges': [
          {'source_id': 'user', 'target_id': 'ent_1611f3f21a8027b7c4f5', 'label': 'knows'},
        ],
      },
    )));
    await tester.pumpAndSettle();

    final canvas = find.byWidgetPredicate((widget) => widget is CustomPaint && widget.painter is GraphPainter3D);
    expect(canvas, findsOneWidget);
    expect(_masked(tester.getRect(canvas)), isTrue);
  });

  testWidgets('a photo picked for the next chat message is masked', (tester) async {
    final dir = Directory.systemTemp.createTempSync('replay-mask');
    addTearDown(() => dir.deleteSync(recursive: true));
    final photo = File('${dir.path}/photo.png')..writeAsBytesSync(_photo);
    final provider = MessageProvider()
      ..selectedFiles.add(photo)
      ..selectedFileTypes.add('image');

    await tester.pumpWidget(_app(Scaffold(
      body: ChangeNotifierProvider<MessageProvider>.value(value: provider, child: const ChatSelectedFilesStrip()),
    )));
    await tester.pump();

    final tileBox = find.byWidgetPredicate(
        (widget) => widget is Container && widget.constraints == const BoxConstraints.tightFor(width: 60, height: 60));
    final tile = find.descendant(of: tileBox, matching: find.byType(Stack)).first;
    expect(tester.getSize(tile).width, 60);
    expect(_masked(tester.getRect(tile)), isTrue);
  });
}
