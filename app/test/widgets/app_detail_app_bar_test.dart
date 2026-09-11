import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/app_detail/widgets/app_detail_app_bar.dart';

Widget _wrap(AppDetailAppBar bar, {Locale locale = const Locale('en')}) => MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: ThemeData.dark(),
      home: Scaffold(appBar: bar),
    );

void main() {
  testWidgets('each named action has a distinct icon and invokes only its callback', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final actions = <String>[];
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(_wrap(AppDetailAppBar(
      appName: 'Notes',
      onBack: () => actions.add('back'),
      onChat: () => actions.add('chat'),
      onOpen: () => actions.add('open'),
      onShare: (_) => actions.add('share'),
      onEdit: () => actions.add('edit'),
      isOwner: true,
    )));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.web), findsOneWidget);
    expect(find.byIcon(FontAwesomeIcons.gear.data), findsNothing);
    final icons = tester.widgetList<FaIcon>(find.byType(FaIcon)).map((icon) => icon.icon).toSet();
    expect(icons, hasLength(4));
    final labels = {'back': 'Back', 'chat': 'Chat with Notes', 'open': 'Open', 'share': 'Share', 'edit': 'Edit'};
    for (final entry in labels.entries) {
      expect(find.byTooltip(entry.value), findsOneWidget);
      final button = find.byKey(ValueKey('app_detail_${entry.key}'));
      // Flutter's Tooltip exposes a semantic tooltip on the button, rather
      // than replacing its semantic label. Native screen readers announce it.
      expect(tester.getSemantics(button).getSemanticsData().tooltip, entry.value);
      expect(tester.getSize(button), const Size(48, 48));
      await tester.tap(button);
      expect(actions, labels.keys.take(actions.length).toList());
    }
    expect(actions, labels.keys.toList());
    expect(tester.takeException(), isNull); // Includes layout overflow at 320 px.
    semantics.dispose();
  });

  testWidgets('only available actions are shown, and loading chat stays labelled but disabled', (tester) async {
    var chats = 0;
    await tester.pumpWidget(_wrap(AppDetailAppBar(appName: 'Notes', onBack: () {})));
    await tester.pumpAndSettle();
    expect(find.byType(IconButton), findsOneWidget);

    await tester.pumpWidget(_wrap(AppDetailAppBar(
      appName: 'Notes',
      onBack: () {},
      onChat: () => chats++,
      chatLoading: true,
    )));
    await tester.pump();
    final chat = find.byKey(const ValueKey('app_detail_chat'));
    expect(tester.widget<IconButton>(chat).onPressed, isNull);
    expect(find.byTooltip('Chat with Notes'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    await tester.tap(chat);
    expect(chats, 0);

    await tester.pumpWidget(_wrap(AppDetailAppBar(appName: 'Notes', onBack: () {}, onChat: () => chats++)));
    await tester.pumpAndSettle();
    await tester.tap(chat);
    expect(chats, 1);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('share receives its own laid-out anchor for the iOS share sheet', (tester) async {
    Rect? shareRect;
    await tester.pumpWidget(_wrap(AppDetailAppBar(
      appName: 'Notes',
      onBack: () {},
      onOpen: () {},
      onShare: (context) {
        final box = context.findRenderObject()! as RenderBox;
        shareRect = box.localToGlobal(Offset.zero) & box.size;
      },
    )));
    await tester.pumpAndSettle();
    final share = find.byKey(const ValueKey('app_detail_share'));
    await tester.tap(share);
    expect(shareRect, isNotNull);
    expect(shareRect!.contains(tester.getCenter(share)), isTrue);
    expect(shareRect!.width, lessThan(60));
    expect(shareRect!.height, 48);
    expect(shareRect!.contains(tester.getCenter(find.byKey(const ValueKey('app_detail_open')))), isFalse);
  });

  testWidgets('action tooltips follow the selected locale', (tester) async {
    const locale = Locale('es');
    final labels = await AppLocalizations.delegate.load(locale);
    await tester.pumpWidget(_wrap(
        AppDetailAppBar(
          appName: 'Notes',
          onBack: () {},
          onChat: () {},
          onOpen: () {},
          onShare: (_) {},
          onEdit: () {},
        ),
        locale: locale));
    await tester.pumpAndSettle();
    for (final text in [labels.back, labels.chatWithAppName('Notes'), labels.open, labels.share, labels.edit]) {
      expect(find.byTooltip(text), findsOneWidget);
    }
    expect(find.byTooltip('Open'), findsNothing);
  });
}
