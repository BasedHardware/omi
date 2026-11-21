import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/env/env.dart';
import 'package:omi/pages/settings/chat_apps/chat_app_widgets.dart';
import 'package:omi/pages/settings/chat_apps/chat_apps_page.dart';
import 'package:omi/services/experiments/chat_apps_gate.dart';
import 'package:omi/ui/ui.dart';
import '../../../helpers/sfpro_font_fixtures.dart';
import 'chat_apps_fixture.dart';

/// Renders Chat Apps with a WhatsApp number configured: the row offers Connect instead of the
/// waitlist, and the sheet uses the one-time-code flow with a WhatsApp bubble.
/// With `--dart-define=WHATSAPP_CONNECT_RENDER_OUTPUT=<dir>` it writes the PR evidence PNGs.
const _output = String.fromEnvironment('WHATSAPP_CONNECT_RENDER_OUTPUT');
final _boundary = GlobalKey();

const _config = ChatAppsConfig(
  enabled: true,
  endpoints: {
    ChatChannel.telegram: telegramEndpoint,
    ChatChannel.imessage: imessageEndpoint,
    ChatChannel.whatsapp: ChatChannelEndpoint(provider: 'keiki', address: '+15550100200'),
  },
);

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
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

Future<void> _capture(WidgetTester tester, String name) async {
  if (_output.isEmpty) return;
  await tester.runAsync(() async {
    final render = _boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = await render.toImage(pixelRatio: 3);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await Directory(_output).create(recursive: true);
    await File('$_output/$name').writeAsBytes(bytes!.buffer.asUint8List());
  });
}

void main() {
  setUpAll(() async {
    Env.init(ChatAppsTestEnv());
    await _loadFonts();
  });
  setUp(initChatAppsTest);

  testWidgets('WhatsApp row connects with a one-time code', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    chatAppLauncher = (uri) async => true;

    final backend = FakeMessagingBackend();
    await tester.pumpWidget(RepaintBoundary(
      key: _boundary,
      child: chatAppsHost(const ChatAppsPage(), provider: backend.provider(config: _config)),
    ));
    await settle(tester);
    expect(find.text('Notify Me'), findsNothing);
    await _capture(tester, '001-mobile-ios-chat-apps-whatsapp-row.png');

    await tester.tap(find.byKey(const ValueKey('chat_apps_row_whatsapp')));
    await settle(tester);
    expect(find.text('Open WhatsApp'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _capture(tester, '002-mobile-ios-whatsapp-connect-code.png');

    await tester.tap(find.byKey(const ValueKey('chat_apps_open_messages')));
    await settle(tester);
    expect(find.text('Send the message in WhatsApp. This screen updates as soon as Omi gets it.'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _capture(tester, '003-mobile-ios-whatsapp-connect-waiting.png');

    Navigator.of(tester.element(find.byType(ChatAppsPage))).pop();
    await settle(tester);
    debugDefaultTargetPlatformOverride = null;
    OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  });
}
